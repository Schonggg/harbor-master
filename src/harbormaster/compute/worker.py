"""In-process compute: corpus jobs already run on daemon threads; this tracks them and optional timed backups."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from harbormaster.config import get_settings
from harbormaster.logging import get_logger

log = get_logger("harbormaster.compute")
_BACKUP_THREAD: threading.Thread | None = None


def compute_status() -> dict:
    from harbormaster.ledger.store import LedgerStore

    workers = [
        t.name
        for t in threading.enumerate()
        if t.name.startswith("hm-") or t.name.startswith("hm-corpus-")
    ]
    job = LedgerStore().latest_job()
    settings = get_settings()
    return {
        "workers": max(settings.worker_threads, 1),
        "active_threads": workers,
        "latest_job": job,
        "backup_interval_hours": settings.backup_interval_hours,
    }


def offload_bytes(key: str, data: bytes, content_type: str) -> dict:
    from harbormaster.ledger.store import LedgerStore
    from harbormaster.storage.factory import get_object_store

    store = get_object_store()
    ref = store.put(key, data, content_type)
    LedgerStore().record_object(ref)
    return {
        "key": ref.key,
        "backend": ref.backend,
        "bytes": ref.bytes,
        "uri": ref.uri,
    }


def backup_now() -> dict:
    from datetime import datetime, timezone

    from harbormaster.config import data_dir
    from harbormaster.ledger.store import LedgerStore

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = data_dir() / "backups" / f"harbormaster-{stamp}.db"
    path = LedgerStore().backup(dest)
    blob = path.read_bytes()
    cloud = offload_bytes(f"backups/{path.name}", blob, "application/octet-stream")
    return {"path": str(path), "bytes": len(blob), "object": cloud}


def start_backup_loop() -> None:
    global _BACKUP_THREAD
    hours = get_settings().backup_interval_hours
    if hours <= 0:
        return
    if _BACKUP_THREAD and _BACKUP_THREAD.is_alive():
        return

    def _loop() -> None:
        interval = max(hours, 0.25) * 3600
        while True:
            time.sleep(interval)
            try:
                backup_now()
                log.info("scheduled_backup_ok", at=datetime.now(timezone.utc).isoformat())
            except Exception as exc:  # noqa: BLE001
                log.warning("scheduled_backup_failed", error=str(exc)[:200])

    _BACKUP_THREAD = threading.Thread(target=_loop, name="hm-backup", daemon=True)
    _BACKUP_THREAD.start()
