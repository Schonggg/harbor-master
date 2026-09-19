"""Commercial ops: backup, object storage, compute, hashed API keys."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from harbormaster.compute.worker import backup_now, compute_status, offload_bytes
from harbormaster.config import get_settings
from harbormaster.keys import generate_api_key, hash_api_key, key_prefix
from harbormaster.ledger.store import LedgerStore
from harbormaster.storage.factory import get_object_store

router = APIRouter()


class IssueKeyBody(BaseModel):
    name: str = Field(default="integration", max_length=80)


@router.get("/ops/status")
def ops_status():
    settings = get_settings()
    store = LedgerStore()
    storage = get_object_store().health()
    objects = store.object_stats()
    return {
        "env": settings.harbormaster_env,
        "auth_required": bool(settings.service_api_key) or store.active_api_key_count() > 0,
        "bootstrap_key": bool(settings.service_api_key),
        "issued_keys": store.active_api_key_count(),
        "storage": {**storage, **objects},
        "compute": compute_status(),
        "objects": store.list_objects(12),
    }


@router.post("/ops/backup")
def backup_db(cloud: bool = True):
    try:
        if cloud:
            return backup_now()
        from datetime import datetime, timezone

        from harbormaster.config import data_dir

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = data_dir() / "backups" / f"harbormaster-{stamp}.db"
        path = LedgerStore().backup(dest)
        return {"path": str(path), "bytes": path.stat().st_size, "object": None}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)[:240]) from exc


@router.get("/keys")
def list_keys():
    return LedgerStore().list_api_keys()


@router.post("/keys")
def issue_key(body: IssueKeyBody):
    raw = generate_api_key()
    issued = LedgerStore().issue_api_key(
        name=body.name,
        raw=raw,
        prefix=key_prefix(raw),
        key_hash=hash_api_key(raw),
    )
    return issued


@router.post("/keys/{key_id}/revoke")
def revoke_key(key_id: str):
    if not LedgerStore().revoke_api_key(key_id):
        raise HTTPException(status_code=404, detail="key not found or already revoked")
    return {"revoked": key_id}


def put_export(name: str, data: bytes, content_type: str) -> dict:
    return offload_bytes(f"exports/{name}", data, content_type)
