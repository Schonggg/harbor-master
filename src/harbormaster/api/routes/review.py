from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from harbormaster.ledger.promoter import Promoter
from harbormaster.ledger.replay import Replayer
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import CaseVerdict, ComparisonStatus, EmailVerdict, PilotDecision, PilotReview

router = APIRouter()

CASE_FIELD = "case"


def _find_run(case_id: str) -> dict | None:
    return LedgerStore().get_run_by_ref(case_id)


def _fv_writings(fv: dict) -> tuple[str, str, str]:
    charge = fv.get("charge") or {}
    left = str((charge.get("left") or {}).get("raw_value") or fv.get("left_value") or "").strip()
    right = str((charge.get("right") or {}).get("raw_value") or fv.get("right_value") or "").strip()
    field = str(fv.get("field") or "").strip()
    return field, left, right


def _lockable_pairs(card: dict, verdict: str = "CLEAR") -> list[tuple[str, str, str]]:
    """Contested SI/BL writings a human stamp can teach and replay.

    Only UNCERTAIN / MISMATCH pairs. Already-MATCH fields (suffix strip, LOCODE, …)
    must not be promoted — replaying them across the corpus would silently flip
    unrelated PILOT mail to CLEAR. The case stamp still records every CLEAR/HOLD.
    """
    del verdict  # kept for call-site compatibility
    out: list[tuple[str, str, str]] = []
    for fv in card.get("field_verdicts") or []:
        if not isinstance(fv, dict):
            continue
        if str(fv.get("rationale") or "").startswith("ledger"):
            continue
        field, left, right = _fv_writings(fv)
        if not field or field == CASE_FIELD or not left or not right:
            continue
        if fv.get("state") in {"UNCERTAIN", "MISMATCH"}:
            out.append((field, left, right))
    return out


def _promote_one(store: LedgerStore, promoter: Promoter, case_id: str, field: str, left: str, right: str, body: CaseVerdictBody, decision: PilotDecision) -> dict | None:
    if store.find_matching_rule(field, left, right):
        return None
    review = PilotReview(
        case_id=case_id,
        field=field,
        decision=decision,
        promote_to_ledger=True,
        reviewer=body.reviewer,
        note=body.note or f"case {body.verdict}",
    )
    rule = promoter.promote(review, left, right)
    if not rule:
        return None
    return rule.model_dump(mode="json")


def _promote_pairs_for_verdict(store: LedgerStore, case_id: str, card: dict, body: CaseVerdictBody, email_id: str = "") -> tuple[list[dict], int]:
    """Case stamp always; contested UNCERTAIN/MISMATCH pairs may replay onto open Pilot mail."""
    pair_decision = (
        PilotDecision.ACCEPT_AS_MATCH if body.verdict == "CLEAR" else PilotDecision.CONFIRM_MISMATCH
    )
    promoter = Promoter(store)
    replayed = 0
    rules: list[dict] = []
    for field, left, right in _lockable_pairs(card, body.verdict):
        dumped = _promote_one(store, promoter, case_id, field, left, right, body, pair_decision)
        if not dumped:
            continue
        replayed += int((Replayer(store).replay(dumped["rule_id"]) or {}).get("updated") or 0)
        rules.append(dumped)
    stamp_left = str(card.get("email_id") or email_id or case_id).strip()
    stamp = _promote_one(
        store,
        promoter,
        case_id,
        CASE_FIELD,
        stamp_left,
        body.verdict,
        body,
        pair_decision,
    )
    if stamp:
        rules.append(stamp)
    return rules, replayed


class ReviewBody(BaseModel):
    case_id: str
    field: str
    decision: PilotDecision
    left_value: str
    right_value: str
    promote_to_ledger: bool = True
    reviewer: str = "pilot"
    note: str = ""


class CaseVerdictBody(BaseModel):
    case_id: str = ""
    verdict: Literal["CLEAR", "HOLD"]
    reviewer: str = "pilot"
    note: str = ""


@router.get("/review/queue")
def review_queue():
    runs = LedgerStore().list_runs()
    return [r for r in runs if r["verdict"] == "PILOT"]


@router.post("/review/decide")
def decide(body: ReviewBody):
    if body.field == CASE_FIELD:
        raise HTTPException(status_code=400, detail="use /review/verdict for case stamps")
    store = LedgerStore()
    review = PilotReview(
        case_id=body.case_id,
        field=body.field,
        decision=body.decision,
        promote_to_ledger=body.promote_to_ledger,
        reviewer=body.reviewer,
        note=body.note,
    )
    rule = Promoter(store).promote(review, body.left_value, body.right_value)
    replay_result = {"updated": 0}
    if rule:
        replay_result = Replayer(store).replay(rule.rule_id)
    return {"review": review.model_dump(mode="json"), "rule": rule.model_dump(mode="json") if rule else None, "replay": replay_result}


@router.post("/review/verdict")
def set_case_verdict(body: CaseVerdictBody):
    """Human closes a whole PILOT mail as CLEAR or HOLD. Contested SI/BL pairs are taught to the ledger."""
    run = _find_run(body.case_id)
    if not run:
        raise HTTPException(status_code=404, detail="case not found")
    store = LedgerStore()
    payload = dict(run.get("payload") or {})
    card = dict(payload.get("card") or {})
    # Stamp the board first. Promote/replay can be slow; a timeout must not leave the mail in PILOT.
    card["verdict"] = body.verdict
    card["pilot_override"] = True
    card["pilot_override_by"] = body.reviewer
    card["pilot_override_note"] = body.note
    payload["card"] = card
    official = payload.get("official")
    if isinstance(official, dict) and official.get("category") == "BL_COMPARISON":
        official = dict(official)
        official["status"] = ComparisonStatus.OK.value if body.verdict == CaseVerdict.CLEAR.value else ComparisonStatus.MISMATCH.value
        official["review_reason"] = None
        payload["official"] = official
        try:
            store.save_verdict(run["email_id"], EmailVerdict.model_validate(official), payload=official)
        except Exception:
            pass
    from harbormaster.report.reply_draft import generate_outbox_from_run

    draft = generate_outbox_from_run({**run, "payload": payload}, body.verdict)
    if draft:
        card["reply_draft"] = draft
        payload["card"] = card
    store.save_run(run["run_id"], run["case_id"], run["email_id"], body.verdict, payload)
    rules, replayed = _promote_pairs_for_verdict(
        store,
        run.get("case_id") or body.case_id,
        card,
        body,
        email_id=str(run.get("email_id") or ""),
    )
    return {
        "case_id": run["case_id"],
        "email_id": run["email_id"],
        "verdict": body.verdict,
        "reviewer": body.reviewer,
        "reply_draft": draft,
        "rules": rules,
        "replay": {"updated": replayed},
    }


class ReopenBody(BaseModel):
    case_id: str = ""
    reviewer: str = "pilot"
    note: str = "reopen to pilot"


@router.post("/review/reopen")
def reopen_to_pilot(body: ReopenBody):
    """Undo a human CLEAR/HOLD: mail returns to Pilot; case stamp and taught pairs from this case are revoked."""
    run = _find_run(body.case_id)
    if not run:
        raise HTTPException(status_code=404, detail="case not found")
    store = LedgerStore()
    payload = dict(run.get("payload") or {})
    card = dict(payload.get("card") or {})
    if not card.get("pilot_override") and str(run.get("verdict") or "").upper() == "PILOT":
        return {
            "case_id": run["case_id"],
            "email_id": run["email_id"],
            "verdict": "PILOT",
            "revoked": [],
            "reason": "already in Pilot",
        }

    case_id = str(run.get("case_id") or body.case_id)
    email_id = str(run.get("email_id") or "")
    revoked: list[str] = []
    undone = 0
    for rule in store.list_rules(active_only=False):
        if not rule.active:
            continue
        if rule.source_case_id != case_id and not (
            rule.field == CASE_FIELD and rule.left_pattern == email_id
        ):
            continue
        store.revoke(rule.rule_id)
        revoked.append(rule.rule_id)
        if rule.field != CASE_FIELD:
            undone += int((Replayer(store).undo(rule.rule_id) or {}).get("updated") or 0)

    card["verdict"] = CaseVerdict.PILOT.value
    card["pilot_override"] = False
    card["pilot_override_by"] = ""
    card["pilot_override_note"] = body.note or "reopen to pilot"
    card.pop("reply_draft", None)
    # Peel ledger paint left on this card from its own rules.
    for fv in card.get("field_verdicts") or []:
        if not isinstance(fv, dict):
            continue
        rat = str(fv.get("rationale") or "")
        if rat.startswith("ledger"):
            fv["state"] = "UNCERTAIN"
            fv["rationale"] = "reopened to pilot"
            if fv.get("winning_strategy") == "ledger":
                fv["winning_strategy"] = None
    payload["card"] = card
    official = payload.get("official")
    if isinstance(official, dict) and official.get("category") == "BL_COMPARISON":
        official = dict(official)
        official["status"] = ComparisonStatus.NEEDS_REVIEW.value
        payload["official"] = official
        try:
            store.save_verdict(email_id, EmailVerdict.model_validate(official), payload=official)
        except Exception:
            pass
    store.save_run(run["run_id"], run["case_id"], email_id, CaseVerdict.PILOT.value, payload)
    return {
        "case_id": run["case_id"],
        "email_id": email_id,
        "verdict": "PILOT",
        "revoked": revoked,
        "replay": {"updated": undone},
        "reviewer": body.reviewer,
    }


@router.get("/review/{case_id}")
def get_case(case_id: str):
    row = _find_run(case_id)
    if not row:
        raise HTTPException(status_code=404, detail="case not found")
    return row
