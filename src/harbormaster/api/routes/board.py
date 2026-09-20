"""GET /api/board — verdict cards for the Bridge frontend."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Body

from harbormaster.ledger.store import LedgerStore

router = APIRouter()


@router.get("/board")
def board():
    store = LedgerStore()
    runs = store.list_runs()
    reviewed_ids = store.list_reviewed_email_ids()
    cards = []
    for run in runs:
        card = dict((run.get("payload") or {}).get("card") or {})
        eid = card.get("email_id") or run.get("email_id")
        if eid:
            card["email_id"] = eid
        card["reviewed"] = eid in reviewed_ids
        cards.append(card)
    counts = Counter(r.get("verdict") for r in runs)
    return {
        "cards": cards,
        "runs": runs,
        "counts": {
            "CLEAR": counts.get("CLEAR", 0),
            "HOLD": counts.get("HOLD", 0),
            "PILOT": counts.get("PILOT", 0),
        },
    }


@router.post("/board/reviewed")
def mark_reviewed(payload: dict = Body(...)):
    email_ids = [str(eid).strip() for eid in (payload.get("email_ids") or []) if str(eid).strip()]
    reviewed = payload.get("reviewed", True)
    reviewed_by = str(payload.get("reviewed_by") or "")
    store = LedgerStore()
    if reviewed:
        store.mark_reviewed(email_ids, reviewed_by=reviewed_by)
    else:
        store.unmark_reviewed(email_ids)
    return {"ok": True, "count": len(email_ids), "reviewed": bool(reviewed)}
