from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from harbormaster.graph.pipeline import run_from_request, run_pipeline
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import EmailMessage, RunRequest
from harbormaster.reliability.chaos import CHAOS_TYPES

router = APIRouter()

# in-memory last chaos for dial demo
_LAST_CHAOS: dict = {}

_SMASH_PREFIX = "chaos_"


class ChaosBody(BaseModel):
    email_id: str | None = None


def _synthetic_email(chaos_type: str) -> EmailMessage:
    """In-memory smash mail. Never loads a 520-inbox SI/BL pair (that 504s on Vercel)."""
    eid = f"{_SMASH_PREFIX}{chaos_type}"
    if chaos_type == "empty_email":
        return EmailMessage(email_id=eid, subject="", body_text="")
    compare = "Please compare the attached shipping instruction and bill of lading."
    if chaos_type == "ocr_garble":
        return EmailMessage(email_id=eid, subject="TO CONFIRM DOCS — chaos smash", body_text=compare)
    if chaos_type == "attachment_corrupt":
        return EmailMessage(
            email_id=eid,
            subject="TO CONFIRM DOCS — chaos smash",
            body_text=compare,
            attachment_paths=["__corrupt__/missing.bin"],
        )
    return EmailMessage(email_id=eid, subject="TO CONFIRM DOCS — chaos smash", body_text=compare)


def _restore_injected_official(store: LedgerStore, *, limit: int = 1) -> int:
    """Re-judge official mails an older smash overwrote. Rules-only, one at a time."""
    restored = 0
    for run in store.list_runs():
        if restored >= limit:
            break
        eid = str(run.get("email_id") or "")
        if eid.startswith(_SMASH_PREFIX):
            continue
        card = (run.get("payload") or {}).get("card") or {}
        codes = card.get("failure_codes") or []
        if "CHAOS_INJECTED" not in codes:
            continue
        try:
            run_from_request(
                RunRequest(email_id=eid, degrade=True, rules_only=True, chaos=[], save_board=True)
            )
            restored += 1
        except Exception:
            continue
    return restored


@router.get("/chaos/types")
def chaos_types():
    return {"types": list(CHAOS_TYPES)}


@router.post("/chaos/reset")
def reset_chaos():
    store = LedgerStore()
    from harbormaster.ledger.repair import repair_ledger_closures

    repair = repair_ledger_closures(store)
    dropped = store.purge_email_prefix(_SMASH_PREFIX)
    pruned = store.prune_duplicate_runs()
    restored = _restore_injected_official(store)
    return {"dropped": dropped, "pruned": pruned, "restored": restored, "ledger_repair": repair}


@router.post("/chaos/{chaos_type}")
def trigger_chaos(chaos_type: str, body: ChaosBody | None = None):
    del body  # live 520 ids are ignored — smashing them 504s and overwrites CLEAR
    if chaos_type not in CHAOS_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown chaos type: {chaos_type}")
    email = _synthetic_email(chaos_type)
    result = run_pipeline(
        email,
        degrade=True,
        chaos=[chaos_type],
        rules_only=True,
        save_board=True,
    )
    payload = result.model_dump(mode="json")
    _LAST_CHAOS[chaos_type] = payload
    return payload
