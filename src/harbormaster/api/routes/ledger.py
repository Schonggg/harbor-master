from __future__ import annotations

from fastapi import APIRouter, HTTPException

from harbormaster.ledger.store import LedgerStore

router = APIRouter()


@router.get("/ledger")
@router.get("/ledger/rules")
def list_ledger():
    return [r.model_dump(mode="json") for r in LedgerStore().list_rules(active_only=False)]


@router.post("/ledger/{rule_id}/revoke")
def revoke_rule(rule_id: str):
    store = LedgerStore()
    existing = {r.rule_id: r for r in store.list_rules(active_only=False)}
    if rule_id not in existing:
        raise HTTPException(status_code=404, detail="rule not found")
    store.revoke(rule_id)
    return {"revoked": rule_id}
