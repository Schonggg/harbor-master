from __future__ import annotations

from fastapi import APIRouter, HTTPException

from harbormaster.api.routes.review import CASE_FIELD
from harbormaster.ledger.promoter import Promoter
from harbormaster.ledger.replay import Replayer
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import PilotDecision, PilotReview

router = APIRouter()


def _backfill_pilot_case_stamps(store: LedgerStore) -> None:
    """Older CLEAR/HOLD stamps that had no SI/BL pair never wrote a ledger row. Restore them.

    Read-path only: never mutates case_runs / verdicts. Safe to call on every GET /ledger.
    """
    promoter = Promoter(store)
    for run in store.list_human_closed_runs():
        card = (run.get("payload") or {}).get("card") or {}
        verdict = str(card.get("verdict") or run.get("verdict") or "")
        if verdict not in {"CLEAR", "HOLD"}:
            continue
        email_id = str(run.get("email_id") or card.get("email_id") or "").strip()
        if not email_id:
            continue
        if store.find_matching_rule(CASE_FIELD, email_id, verdict):
            continue
        decision = (
            PilotDecision.ACCEPT_AS_MATCH if verdict == "CLEAR" else PilotDecision.CONFIRM_MISMATCH
        )
        review = PilotReview(
            case_id=str(run.get("case_id") or email_id),
            field=CASE_FIELD,
            decision=decision,
            promote_to_ledger=True,
            reviewer=str(card.get("pilot_override_by") or "pilot"),
            note="backfill case stamp",
        )
        promoter.promote(review, email_id, verdict)


@router.get("/ledger")
@router.get("/ledger/rules")
def list_ledger():
    """List ledger rules. May backfill missing case stamps; never changes board verdicts."""
    store = LedgerStore()
    _backfill_pilot_case_stamps(store)
    return [r.model_dump(mode="json") for r in store.list_rules(active_only=False)]


@router.post("/ledger/{rule_id}/revoke")
def revoke_rule(rule_id: str):
    store = LedgerStore()
    existing = {r.rule_id: r for r in store.list_rules(active_only=False)}
    if rule_id not in existing:
        raise HTTPException(status_code=404, detail="rule not found")
    rule = existing[rule_id]
    store.revoke(rule_id)
    undone = {"updated": 0, "rule_id": rule_id}
    # Case stamps are provenance only — peeling them must not re-open human CLEAR/HOLD.
    if rule.field != "case":
        undone = Replayer(store).undo(rule_id)
    return {"revoked": rule_id, "undone": undone}
