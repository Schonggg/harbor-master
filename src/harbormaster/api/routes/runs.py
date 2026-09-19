from __future__ import annotations

from fastapi import APIRouter, HTTPException

from harbormaster.graph.pipeline import run_from_request, start_corpus_job
from harbormaster.ingest.loader_adapter import LoaderAdapter
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import RunRequest, is_demo_email_id

router = APIRouter()


@router.get("/inbox")
def inbox_catalog(source: str = "official"):
    """Official SDOC inbox as the Bridge sees it — subjects, not just ids."""
    loader = LoaderAdapter()
    items = loader.catalog(source=source)
    return {"items": items, "count": len(items), "inbox": loader.health()}


@router.get("/emails")
def list_emails(source: str = "auto"):
    loader = LoaderAdapter()
    return {"email_ids": loader.list_email_ids(source=source), "inbox": loader.health()}


@router.get("/emails/{email_id}")
def get_email(email_id: str, source: str = "auto"):
    """Original message text, so the Bridge can highlight evidence in place."""
    try:
        return LoaderAdapter().load(email_id, source=source).model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/run")
def post_run(req: RunRequest):
    if req.full:
        job_id = start_corpus_job(
            source=req.source,
            rules_only=req.rules_only,
            two_value=req.two_value if req.two_value is not None else True,
            save_board=bool(req.save_board),
        )
        return {"job_id": job_id, "status": "queued", "mode": "full"}
    try:
        result = run_from_request(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.get("/run/status")
def run_status():
    job = LedgerStore().latest_job()
    if not job:
        return {"status": "idle"}
    return job


@router.get("/run/jobs/{job_id}")
def get_job(job_id: str):
    row = LedgerStore().get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return row


def _has_writing(side) -> bool:
    if not isinstance(side, dict):
        return False
    val = side.get("raw_value")
    return val is not None and str(val).strip() != ""


def _field_lockable(fv: dict) -> bool:
    """True only when both SI and BL writings exist — Ledger stores a pair."""
    if fv.get("state") not in ("UNCERTAIN", "MISMATCH"):
        return False
    charge = fv.get("charge")
    if not isinstance(charge, dict):
        return False
    return _has_writing(charge.get("left")) and _has_writing(charge.get("right"))


def _board_payload(payload: dict) -> dict:
    card = payload.get("card") if isinstance(payload, dict) else {}
    if not isinstance(card, dict):
        card = {}
    fields = []
    lockable = False
    for fv in card.get("field_verdicts") or []:
        if not isinstance(fv, dict):
            continue
        charge = fv.get("charge")
        slim = None
        if isinstance(charge, dict):
            left = charge.get("left") if isinstance(charge.get("left"), dict) else {}
            right = charge.get("right") if isinstance(charge.get("right"), dict) else {}
            slim = {
                "left": {"raw_value": left.get("raw_value"), "confidence": left.get("confidence")},
                "right": {"raw_value": right.get("raw_value"), "confidence": right.get("confidence")},
            }
        if _field_lockable(fv):
            lockable = True
        fields.append(
            {
                "field": fv.get("field"),
                "state": fv.get("state"),
                "charge": slim,
                "winning_strategy": fv.get("winning_strategy"),
                "rationale": (fv.get("rationale") or "")[:120],
                "risk_level": fv.get("risk_level"),
                "advise": (fv.get("advise") or "")[:160],
                "exposure_usd": fv.get("exposure_usd"),
                "pleas": [
                    {
                        "strategy": p.get("strategy"),
                        "accepted": p.get("accepted"),
                        "argument": (p.get("argument") or "")[:160],
                        "transformed_left": p.get("transformed_left"),
                        "transformed_right": p.get("transformed_right"),
                    }
                    for p in (fv.get("pleas") or [])
                    if isinstance(p, dict)
                ],
            }
        )
    return {
        "card": {
            "subject": card.get("subject"),
            "verdict": card.get("verdict"),
            "scout": card.get("scout"),
            "degraded": card.get("degraded"),
            "email_id": card.get("email_id"),
            "failure_codes": card.get("failure_codes") or [],
            "ai_resolved": bool(card.get("ai_resolved")),
            "ai_pilot_note": card.get("ai_pilot_note") or "",
            "pilot_override": bool(card.get("pilot_override")),
            "pilot_override_note": card.get("pilot_override_note") or "",
            "reply_draft": (card.get("reply_draft") or "")[:2500] or None,
            "field_verdicts": fields,
            "lockable": lockable,
        },
        "gold_label": payload.get("gold_label"),
    }


@router.get("/runs")
def list_runs():
    store = LedgerStore()
    rows = store.list_runs()
    if store.backend == "postgres":
        rows = [r for r in rows if not is_demo_email_id(r.get("email_id"))]
    return [
        {
            "run_id": r["run_id"],
            "case_id": r["case_id"],
            "email_id": r["email_id"],
            "verdict": r["verdict"],
            "created_at": r["created_at"],
            "payload": _board_payload(r.get("payload") or {}),
        }
        for r in rows
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    row = LedgerStore().get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    return row
