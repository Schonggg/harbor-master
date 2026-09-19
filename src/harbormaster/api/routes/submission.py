"""Official submission export + inbox /submit."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from harbormaster.config import data_dir
from harbormaster.ingest.loader_adapter import LoaderAdapter
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import EmailVerdict
from harbormaster.report.submission import validate_submission, write_submission

router = APIRouter()


def _current_payload() -> tuple[dict, list[str]]:
    store = LedgerStore()
    verdicts = store.list_verdicts()
    payload = {eid: v.as_submission_dict() for eid, v in verdicts.items()}
    loader = LoaderAdapter()
    required = loader.required_email_ids()
    return payload, required


@router.get("/submission")
def get_submission():
    payload, required = _current_payload()
    missing = [i for i in required if i not in payload]
    return {
        "count": len(payload),
        "required": len(required),
        "missing": missing[:50],
        "complete": not missing,
        "preview": dict(list(payload.items())[:5]),
    }


@router.get("/submission/export")
def export_submission():
    payload, required = _current_payload()
    try:
        submission = validate_submission(payload, required)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    path = write_submission(
        {eid: EmailVerdict.model_validate(rec) for eid, rec in payload.items()},
        required,
        data_dir() / "submission.json",
    )
    blob = path.read_bytes()
    cloud = None
    try:
        from harbormaster.api.routes.ops import put_export

        cloud = put_export("submission.json", blob, "application/json")
    except Exception:
        cloud = None
    return {"path": str(path), "count": len(submission.root), "object": cloud}


@router.post("/submission/submit")
def post_submission():
    payload, required = _current_payload()
    try:
        submission = validate_submission(payload, required)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    loader = LoaderAdapter()
    if not loader.inbox_reachable():
        raise HTTPException(status_code=503, detail="inbox is not reachable")
    score = loader.submit(submission.as_dict())
    return {"score": score, "count": len(submission.root)}
