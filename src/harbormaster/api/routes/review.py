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
    """Human closes a whole PILOT mail as CLEAR or HOLD. No LLM. No field pair required."""
    run = _find_run(body.case_id)
    if not run:
        raise HTTPException(status_code=404, detail="case not found")
    store = LedgerStore()
    payload = dict(run.get("payload") or {})
    card = dict(payload.get("card") or {})
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
    return {
        "case_id": run["case_id"],
        "email_id": run["email_id"],
        "verdict": body.verdict,
        "reviewer": body.reviewer,
        "reply_draft": draft,
    }


@router.get("/review/{case_id}")
def get_case(case_id: str):
    row = _find_run(case_id)
    if not row:
        raise HTTPException(status_code=404, detail="case not found")
    return row
