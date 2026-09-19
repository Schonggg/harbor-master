"""Pilot-deck aliases used by the spec. Bridge still calls /api/review/*."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from harbormaster.api.routes.review import CaseVerdictBody, ReviewBody, decide as review_decide, review_queue, set_case_verdict
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import PilotDecision

router = APIRouter()


class PilotDecideBody(BaseModel):
    field: str
    decision: PilotDecision
    left_value: str = ""
    right_value: str = ""
    promote_to_ledger: bool = True
    reviewer: str = "pilot"
    note: str = ""
    case_id: str | None = None


@router.get("/pilot/queue")
def pilot_queue():
    return review_queue()


@router.post("/pilot/{email_id}/decide")
def pilot_decide(email_id: str, body: PilotDecideBody):
    case_id = body.case_id
    if not case_id:
        for run in LedgerStore().list_runs():
            if run.get("email_id") == email_id:
                case_id = run.get("case_id") or run.get("run_id")
                break
    if not case_id:
        raise HTTPException(status_code=404, detail=f"no case for email {email_id}")
    payload = ReviewBody(
        case_id=case_id,
        field=body.field,
        decision=body.decision,
        left_value=body.left_value,
        right_value=body.right_value,
        promote_to_ledger=body.promote_to_ledger,
        reviewer=body.reviewer,
        note=body.note,
    )
    return review_decide(payload)


@router.post("/pilot/{email_id}/verdict")
def pilot_verdict(email_id: str, body: CaseVerdictBody):
    case_id = body.case_id or email_id
    return set_case_verdict(
        CaseVerdictBody(case_id=case_id, verdict=body.verdict, reviewer=body.reviewer, note=body.note)
    )
