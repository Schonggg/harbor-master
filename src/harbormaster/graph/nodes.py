"""Layer nodes for the pipeline."""

from __future__ import annotations

from pathlib import Path

from harbormaster.court.judge import Judge
from harbormaster.graph.state import PipelineState
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import (
    COMPARE_FIELDS,
    Category,
    CaseVerdict,
    CourtState,
    EvidenceSource,
    FailureCode,
    PilotDecision,
)
from harbormaster.official import assemble, decided_by_of
from harbormaster.official.compare import exact_defect_fields
from harbormaster.reader.extractor import FieldExtractor
from harbormaster.reader.health_check import (
    classify_doc_kind,
    health_check,
    pair_si_bl,
    split_inline_si_bl,
)
from harbormaster.reliability.chaos import apply_chaos, corrupt_extracted, normalize_flags
from harbormaster.report.reply_draft import draft_reply
from harbormaster.report.submission import build_bridge_submission, build_official_verdict
from harbormaster.report.verdict import build_card
from harbormaster.risk.engine import RiskEngine
from harbormaster.scout.router import ScoutRouter

_HARD = {
    FailureCode.EMPTY_EMAIL,
    FailureCode.ATTACHMENT_CORRUPT,
    FailureCode.LLM_TIMEOUT,
    FailureCode.OCR_GARBLED,
}


def hard_failures_present(state: PipelineState) -> bool:
    return bool(_HARD & set(state.failures))


def node_chaos(state: PipelineState) -> PipelineState:
    if state.chaos and state.email:
        state.email, codes = apply_chaos(state.email, state.chaos)
        state.failures.extend(codes)
        flags = set(normalize_flags(state.chaos))
        if "llm_timeout" in flags:
            state.degrade = True
    return state


def node_scout(state: PipelineState) -> PipelineState:
    assert state.email
    router = ScoutRouter(degrade=state.degrade or state.rules_only)
    state.scout = router.route(state.email)
    return state


def node_reader(state: PipelineState) -> PipelineState:
    assert state.email
    extractor = FieldExtractor(degrade=state.degrade, rules_only=state.rules_only)
    docs = []
    for path_str in state.email.attachment_paths:
        path = Path(path_str)
        if path.exists():
            docs.append(extractor.extract_path(path))
        else:
            from harbormaster.models import ExtractedDocument

            docs.append(
                ExtractedDocument(
                    filename=path.name,
                    parser_used="corrupt",
                    text="",
                    kind="unknown",
                )
            )

    if not docs:
        inline = split_inline_si_bl(state.email.body_text)
        if inline:
            si_text, bl_text = inline
            docs.append(
                extractor.extract_text(si_text, filename="si.txt", source=EvidenceSource.EMAIL_BODY)
            )
            docs[-1].kind = "si"
            docs.append(
                extractor.extract_text(bl_text, filename="bl.txt", source=EvidenceSource.EMAIL_BODY)
            )
            docs[-1].kind = "bl"
        elif state.email.body_text.strip():
            docs.append(
                extractor.extract_text(
                    state.email.body_text, filename="body.txt", source=EvidenceSource.EMAIL_BODY
                )
            )

    for doc in docs:
        if doc.kind in {"unknown", "other"}:
            doc.kind = classify_doc_kind(doc)  # type: ignore[assignment]

    if "corrupt_field" in normalize_flags(state.chaos):
        if docs:
            docs[0] = corrupt_extracted(docs[0]) or docs[0]

    state.docs = docs
    si, bl = pair_si_bl(docs)
    state.left_doc = si
    state.right_doc = bl
    if state.left_doc is None and docs:
        state.left_doc = docs[0]
    if state.right_doc is None and len(docs) > 1:
        state.right_doc = docs[1]
    elif state.right_doc is None:
        state.right_doc = state.left_doc

    if state.email.meta.get("soft"):
        for doc in (state.left_doc, state.right_doc):
            if not doc:
                continue
            fv = doc.fields.get("vessel_voyage")
            if fv:
                doc.fields["vessel_voyage"] = fv.model_copy(update={"confidence": 0.58})

    category = state.scout.category if state.scout else Category.GENERAL
    if category == Category.BL_COMPARISON:
        state.health = health_check(state.email, docs, si=si, bl=bl)

    if state.degrade:
        state.failures.append(FailureCode.DEGRADED_RULES_ONLY)
    return state


def node_court(state: PipelineState) -> PipelineState:
    assert state.email
    store = LedgerStore()
    risk = RiskEngine()
    category = state.scout.category if state.scout else Category.GENERAL
    health = state.health

    decided = decided_by_of(state.scout)
    if category != Category.BL_COMPARISON:
        official = assemble(category=category, decided_by=decided)
        card = build_card(
            email=state.email,
            scout=state.scout,
            field_verdicts=[],
            verdict=CaseVerdict.CLEAR,
            exposure=0.0,
            failures=state.failures,
            degraded=state.degrade or (state.scout.degraded if state.scout else False),
        )
        card.official = official
        card.reply_draft = draft_reply(card)
        if hard_failures_present(state):
            card.verdict = CaseVerdict.PILOT
            state.interrupt = "pilot_review"
        state.card = card
        state.official = official
        return state

    if health and not health.ok:
        official = assemble(
            category=Category.BL_COMPARISON,
            gate_reason=health.reason,
            decided_by=decided,
        )
        card = build_card(
            email=state.email,
            scout=state.scout,
            field_verdicts=[],
            verdict=CaseVerdict.PILOT,
            exposure=0.0,
            failures=state.failures,
            degraded=state.degrade,
        )
        card.official = official
        card.reply_draft = draft_reply(card)
        state.card = card
        state.official = official
        state.interrupt = "pilot_review"
        return state

    if not state.left_doc or not state.right_doc:
        official = assemble(category=Category.BL_COMPARISON, decided_by=decided)
        card = build_card(
            email=state.email,
            scout=state.scout,
            field_verdicts=[],
            verdict=CaseVerdict.CLEAR,
            exposure=0.0,
            failures=state.failures,
            degraded=state.degrade,
        )
        card.official = official
        card.reply_draft = draft_reply(card)
        state.card = card
        state.official = official
        return state
    judge = Judge(two_value=state.two_value)
    fields = list(COMPARE_FIELDS)
    if not state.two_value:
        extra = sorted(set(state.left_doc.fields) | set(state.right_doc.fields))
        fields = list(dict.fromkeys([*fields, *extra]))
    verdicts, transcript = judge.try_case(
        state.left_doc, state.right_doc, case_id=state.email.email_id, fields=fields
    )

    adjusted = []
    for fv in verdicts:
        if fv.charge:
            rule = store.find_matching_rule(
                fv.field, fv.charge.left.raw_value, fv.charge.right.raw_value
            )
            if rule:
                if rule.decision == PilotDecision.ACCEPT_AS_MATCH:
                    fv = fv.model_copy(
                        update={
                            "state": CourtState.MATCH,
                            "rationale": f"ledger:{rule.rule_id}",
                            "winning_strategy": "ledger",
                        }
                    )
                elif rule.decision == PilotDecision.CONFIRM_MISMATCH:
                    fv = fv.model_copy(
                        update={
                            "state": CourtState.MISMATCH,
                            "rationale": f"ledger:{rule.rule_id}",
                        }
                    )
        adjusted.append(fv)

    adjusted = risk.enrich(adjusted)
    hard_failures = {
        FailureCode.EMPTY_EMAIL,
        FailureCode.ATTACHMENT_CORRUPT,
        FailureCode.LLM_TIMEOUT,
        FailureCode.OCR_GARBLED,
    }
    force_pilot = bool(hard_failures & set(state.failures)) or (
        state.scout is not None and state.scout.label.value == "unknown" and state.degrade
    )
    verdict = risk.rollup(adjusted, force_pilot=force_pilot)
    if hard_failures & set(state.failures):
        verdict = CaseVerdict.PILOT

    pairs: dict[str, tuple[str, str]] = {}
    for field in COMPARE_FIELDS:
        left_fv = state.left_doc.fields.get(field)
        right_fv = state.right_doc.fields.get(field)
        if field == "gross_weight_kg":
            left_fv = left_fv or state.left_doc.fields.get("gross_weight")
            right_fv = right_fv or state.right_doc.fields.get("gross_weight")
        if left_fv and right_fv:
            pairs[field] = (left_fv.raw_value, right_fv.raw_value)
    official = assemble(
        category=Category.BL_COMPARISON,
        defect_fields=exact_defect_fields(pairs),
        decided_by=decided,
    )

    card = build_card(
        email=state.email,
        scout=state.scout,
        field_verdicts=adjusted,
        verdict=verdict,
        exposure=risk.total_exposure(adjusted),
        failures=state.failures,
        degraded=state.degrade,
    )
    card.official = official
    card.reply_draft = draft_reply(card)
    state.card = card
    state.transcript = transcript
    state.official = official
    if verdict == CaseVerdict.PILOT:
        state.interrupt = "pilot_review"
    return state


def node_report(state: PipelineState) -> PipelineState:
    assert state.card and state.email
    official = state.official or build_official_verdict(state.card)
    state.official = official
    state.submission = official.as_submission_dict()
    store = LedgerStore()
    store.save_verdict(state.email.email_id, official, payload=state.submission)
    if state.save_board:
        store.save_run(
            run_id=state.card.case_id,
            case_id=state.card.case_id,
            email_id=state.email.email_id,
            verdict=state.card.verdict.value,
            payload={
                "card": state.card.model_dump(mode="json"),
                "transcript": state.transcript.model_dump(mode="json") if state.transcript else None,
                "submission": state.submission,
                "official": official.as_submission_dict(),
                "bridge": build_bridge_submission(state.email, state.card),
            },
        )
    return state
