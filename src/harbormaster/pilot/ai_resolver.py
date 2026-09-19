"""AI Pilot closer (not wired into the live pipeline). Kept for tests and offline experiments."""

from __future__ import annotations

from typing import Any

from harbormaster.config import load_prompt
from harbormaster.court.aggregate import aggregate
from harbormaster.llm.client import get_llm_client, llm_available
from harbormaster.models import (
    CaseVerdict,
    ComparisonStatus,
    CourtState,
    EmailVerdict,
    FailureCode,
    FieldVerdict,
    Plea,
)
from harbormaster.report.reply_draft import draft_reply
from harbormaster.report.verdict import build_card
from harbormaster.risk.engine import RiskEngine

_HARD = {
    FailureCode.EMPTY_EMAIL,
    FailureCode.ATTACHMENT_CORRUPT,
    FailureCode.LLM_TIMEOUT,
    FailureCode.OCR_GARBLED,
}


def resolve_pilot(state) -> bool:
    """Mutate a PILOT pipeline state into CLEAR or HOLD. Returns True if closed."""
    card = state.card
    if card is None or card.verdict != CaseVerdict.PILOT:
        return False
    if state.degrade or not llm_available():
        return False

    payload = _ask_model(state)
    if not payload:
        return False

    risk = RiskEngine()
    fields = list(card.field_verdicts)
    by_name = {row.get("field"): row for row in payload.get("fields") or [] if isinstance(row, dict)}
    next_fields: list[FieldVerdict] = []
    resolved_n = 0
    for fv in fields:
        row = by_name.get(fv.field)
        if fv.state != CourtState.UNCERTAIN or not row:
            next_fields.append(fv)
            continue
        decision = str(row.get("decision") or "").strip().lower()
        reason = str(row.get("reason") or "AI Pilot").strip()
        conf = _as_conf(row.get("confidence"))
        if decision in {"accept_as_match", "match", "clear", "same"}:
            next_fields.append(_apply_field(fv, CourtState.MATCH, reason, conf))
            resolved_n += 1
        elif decision in {"confirm_mismatch", "mismatch", "hold", "different"}:
            next_fields.append(_apply_field(fv, CourtState.MISMATCH, reason, conf))
            resolved_n += 1
        else:
            next_fields.append(fv)

    next_fields = risk.enrich(next_fields)
    still_grey = any(fv.state == CourtState.UNCERTAIN for fv in next_fields)
    case_verdict = str(payload.get("case_verdict") or "").strip().upper()
    note = str(payload.get("reason") or "").strip()

    if still_grey or not next_fields:
        if case_verdict == "CLEAR":
            verdict = CaseVerdict.CLEAR
        elif case_verdict == "HOLD":
            verdict = CaseVerdict.HOLD
        elif _HARD & set(state.failures):
            verdict = CaseVerdict.HOLD
        else:
            verdict = CaseVerdict.HOLD if still_grey else risk.rollup(next_fields)
        if still_grey:
            forced = CourtState.MISMATCH if verdict == CaseVerdict.HOLD else CourtState.MATCH
            next_fields = [
                _apply_field(fv, forced, note or "AI Pilot closed residual grey zone", 0.5)
                if fv.state == CourtState.UNCERTAIN
                else fv
                for fv in next_fields
            ]
            next_fields = risk.enrich(next_fields)
            resolved_n += 1
    else:
        verdict = risk.rollup(next_fields)
        if verdict == CaseVerdict.PILOT:
            verdict = CaseVerdict.HOLD if case_verdict == "HOLD" else CaseVerdict.CLEAR

    if verdict == CaseVerdict.PILOT:
        verdict = CaseVerdict.HOLD

    official = _official_for(state, next_fields, verdict)
    new_card = build_card(
        email=state.email,
        scout=state.scout,
        field_verdicts=next_fields,
        verdict=verdict,
        exposure=risk.total_exposure(next_fields),
        failures=state.failures,
        degraded=state.degrade,
    )
    new_card.case_id = card.case_id
    new_card.official = official
    new_card.reply_draft = draft_reply(new_card)
    new_card.ai_resolved = True
    new_card.ai_pilot_note = note or f"AI Pilot closed {resolved_n} grey field(s) as {verdict.value}."
    state.card = new_card
    state.official = official
    state.interrupt = None
    if state.transcript:
        state.transcript.add(
            "note",
            "ai_pilot",
            {"verdict": verdict.value, "reason": new_card.ai_pilot_note, "fields": resolved_n},
        )
    return True


def _apply_field(fv: FieldVerdict, state: CourtState, reason: str, conf: float) -> FieldVerdict:
    plea = Plea(
        strategy="ai_pilot",
        accepted=state == CourtState.MATCH,
        argument=reason,
        confidence=conf,
    )
    return fv.model_copy(
        update={
            "state": state,
            "pleas": [*(fv.pleas or []), plea],
            "winning_strategy": "ai_pilot" if state == CourtState.MATCH else fv.winning_strategy,
            "rationale": f"ai-pilot: {reason}",
        }
    )


def _official_for(state, fields: list[FieldVerdict], verdict: CaseVerdict) -> EmailVerdict:
    from harbormaster.models import Category

    category = state.scout.category if state.scout else Category.GENERAL
    if category != Category.BL_COMPARISON:
        return EmailVerdict(category=category)
    health = state.health
    if health and not health.ok:
        return EmailVerdict(
            category=Category.BL_COMPARISON,
            status=ComparisonStatus.NEEDS_REVIEW if verdict != CaseVerdict.HOLD else ComparisonStatus.MISMATCH,
            review_reason=health.reason,
        )
    has_defect, defect_fields = aggregate(fields)
    if verdict == CaseVerdict.HOLD or has_defect:
        return EmailVerdict(
            category=Category.BL_COMPARISON,
            status=ComparisonStatus.MISMATCH,
            has_defect=True,
            defect_fields=defect_fields or [fv.field for fv in fields if fv.state == CourtState.MISMATCH],
        )
    return EmailVerdict(category=Category.BL_COMPARISON, status=ComparisonStatus.OK)


def _ask_model(state) -> dict[str, Any] | None:
    card = state.card
    email = state.email
    rows = []
    for fv in card.field_verdicts:
        if fv.state != CourtState.UNCERTAIN:
            continue
        charge = fv.charge
        rows.append(
            {
                "field": fv.field,
                "left": charge.left.raw_value if charge else "",
                "right": charge.right.raw_value if charge else "",
                "left_confidence": charge.left.confidence if charge else None,
                "right_confidence": charge.right.confidence if charge else None,
                "failed_strategies": [p.strategy for p in fv.pleas or []],
                "rationale": fv.rationale,
            }
        )
    user = {
        "email_id": email.email_id if email else "",
        "subject": email.subject if email else card.subject,
        "category": state.scout.category.value if state.scout else "",
        "failures": [c.value for c in state.failures],
        "uncertain_fields": rows,
        "body_excerpt": (email.body_text or "")[:1500] if email else "",
    }
    prompt = load_prompt("pilot.md")
    try:
        client = get_llm_client()
        return client.cached_json(
            "ai_pilot",
            str(user),
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": _as_user_text(user)},
            ],
        )
    except Exception:
        return None


def _as_user_text(user: dict[str, Any]) -> str:
    import json

    return json.dumps(user, ensure_ascii=False, indent=2)


def _as_conf(value: Any) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.6
    return max(0.0, min(1.0, n))
