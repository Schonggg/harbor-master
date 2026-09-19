"""GET /api/board — verdict cards for the Bridge frontend."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter

from harbormaster.ledger.store import LedgerStore

router = APIRouter()


@router.get("/board")
def board():
    runs = LedgerStore().list_runs()
    cards = []
    for run in runs:
        card = (run.get("payload") or {}).get("card") or {}
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
