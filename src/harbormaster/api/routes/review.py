from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from harbormaster.ledger.promoter import Promoter
from harbormaster.ledger.replay import Replayer
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import CaseVerdict, ComparisonStatus, EmailVerdict, PilotDecision, PilotReview

router = APIRouter()


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


def _find_run(case_id: str) -> dict | None:
    return LedgerStore().get_run_by_ref(case_id)


def _lockable_pairs(card: dict) -> list[tuple[str, str, str]]:
    """SI/BL writings a human stamp can teach the ledger. No pair → nothing to replay."""
    out: list[tuple[str, str, str]] = []
    for fv in card.get("field_verdicts") or []:
        if not isinstance(fv, dict):
            continue
        if fv.get("state") not in {"UNCERTAIN", "MISMATCH"}:
            continue
        if str(fv.get("rationale") or "").startswith("ledger"):
            continue
        charge = fv.get("charge") or {}
        left = str((charge.get("left") or {}).get("raw_value") or fv.get("left_value") or "").strip()
        right = str((charge.get("right") or {}).get("raw_value") or fv.get("right_value") or "").strip()
        field = str(fv.get("field") or "").strip()
        if field and left and right:
            out.append((field, left, right))
    return out


def _promote_pairs_for_verdict(store: LedgerStore, case_id: str, card: dict, body: CaseVerdictBody) -> tuple[list[dict], int]:
    """Closing CLEAR/HOLD teaches remaining contested pairs so later mail can reuse the ruling."""
    decision = (
        PilotDecision.ACCEPT_AS_MATCH if body.verdict == "CLEAR" else PilotDecision.CONFIRM_MISMATCH
    )
    promoter = Promoter(store)
    replayed = 0
    rules: list[dict] = []
    for field, left, right in _lockable_pairs(card):
        if store.find_matching_rule(field, left, right):
            continue
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
            continue
        replayed += int((Replayer(store).replay(rule.rule_id) or {}).get("updated") or 0)
        rules.append(rule.model_dump(mode="json"))
    return rules, replayed


@router.get("/review/queue")
def review_queue():
    runs = LedgerStore().list_runs()
    return [r for r in runs if r["verdict"] == "PILOT"]


@router.post("/review/decide")
def decide(body: ReviewBody):
    review = PilotReview(
        case_id=body.case_id,
        field=body.field,
        decision=body.decision,
        promote_to_ledger=body.promote_to_ledger,
        reviewer=body.reviewer,
        note=body.note,
    )
    rule = Promoter().promote(review, body.left_value, body.right_value)
    replay_result = {"updated": 0}
    if rule:
        replay_result = Replayer().replay(rule.rule_id)
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
    rules, replayed = _promote_pairs_for_verdict(store, run.get("case_id") or body.case_id, card, body)
    fresh = _find_run(body.case_id) or run
    payload = dict(fresh.get("payload") or payload)
    card = dict(payload.get("card") or card)
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

    draft = generate_outbox_from_run({**fresh, "payload": payload}, body.verdict)
    if draft:
        card["reply_draft"] = draft
        payload["card"] = card
    store.save_run(fresh["run_id"], fresh["case_id"], fresh["email_id"], body.verdict, payload)
    return {
        "case_id": fresh["case_id"],
        "email_id": fresh["email_id"],
        "verdict": body.verdict,
        "reviewer": body.reviewer,
        "reply_draft": draft,
        "rules": rules,
        "replay": {"updated": replayed},
    }


@router.get("/review/{case_id}")
def get_case(case_id: str):
    row = _find_run(case_id)
    if not row:
        raise HTTPException(status_code=404, detail="case not found")
    return row
