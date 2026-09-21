"""GET /api/board — verdict cards for the Bridge frontend."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Body, HTTPException

from harbormaster.ledger.store import LedgerStore
from harbormaster.models import is_chaos_email_id, is_demo_email_id

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
    # Header / hub tallies are the official berth only — smash rows stay on Chaos / Pilot filters.
    official = [
        r for r in runs
        if not is_chaos_email_id(r.get("email_id")) and not is_demo_email_id(r.get("email_id"))
    ]
    counts = Counter(r.get("verdict") for r in official)
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


@router.post("/board/rebuild")
def rebuild_board(payload: dict = Body(default={})):
    """Wipe Ledger + human stamps, then re-judge official mail without ledger memory.

    Inbox emails stay. LLM cache stays so the first AI pass can replay quickly.
    Body: { confirm: true, use_ai: true }.
    """
    if not (payload or {}).get("confirm"):
        raise HTTPException(status_code=400, detail="confirm=true required")
    use_ai = bool((payload or {}).get("use_ai", True))
    store = LedgerStore()
    wiped = store.wipe_board_for_rebuild()
    store.purge_demo_runs()
    store.purge_email_prefix("chaos_")

    from harbormaster.graph.pipeline import run_from_request
    from harbormaster.ingest.loader_adapter import LoaderAdapter
    from harbormaster.models import RunRequest

    loader = LoaderAdapter()
    official = store.list_inbox_ids() or loader.list_email_ids(source="official")
    official = [eid for eid in official if not is_demo_email_id(eid) and not is_chaos_email_id(eid)]
    seeded = []
    # Judge the first email in this request so the board is not blank after wipe.
    if official:
        try:
            result = run_from_request(
                RunRequest(
                    email_id=official[0],
                    rules_only=not use_ai,
                    degrade=not use_ai,
                    two_value=True,
                    save_board=True,
                )
            )
            seeded.append(
                {
                    "email_id": official[0],
                    "verdict": result.card.verdict.value,
                    "case_id": result.card.case_id,
                }
            )
        except Exception as exc:  # noqa: BLE001
            seeded.append({"email_id": official[0], "error": str(exc)[:200]})
    return {
        "ok": True,
        "wiped": wiped,
        "use_ai": use_ai,
        "official": len(official),
        "seeded": seeded,
        "queued": max(0, len(official) - len([s for s in seeded if "verdict" in s])),
        "reason": "board rebuilt · ledger cleared · re-judging official inbox",
    }