"""Load official SDOC inbox onto the Bridge board."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter

from harbormaster.config import data_dir, is_serverless
from harbormaster.graph.pipeline import run_from_request, start_corpus_job
from harbormaster.ingest.loader_adapter import LoaderAdapter
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import RunRequest, is_demo_email_id

router = APIRouter()

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"
PREVIEW = 8
SERVERLESS_BATCH = 1


def _hosted(store: LedgerStore) -> bool:
    return is_serverless() or store.backend == "postgres"


def _run_email(email_id: str, *, rules_only: bool) -> dict:
    result = run_from_request(
        RunRequest(
            email_id=email_id,
            rules_only=rules_only,
            degrade=rules_only,
            two_value=True,
            save_board=True,
        )
    )
    return {
        "email_id": email_id,
        "verdict": result.card.verdict.value,
        "case_id": result.card.case_id,
        "category": result.official.category.value if result.official else None,
        "subject": result.card.subject,
    }


def _local_demo_ids(loader: LoaderAdapter) -> list[str]:
    return [i for i in loader.list_email_ids(source="local") if is_demo_email_id(i)]


def seed_demos_if_empty() -> dict:
    """Local empty board only. Public Vercel never paints the 14-demo replay."""
    store = LedgerStore()
    if _hosted(store):
        return {"seeded": 0, "reason": "hosted never uses demo fixtures"}
    if store.list_runs():
        return {"seeded": 0, "reason": "already filled"}
    if store.inbox_count():
        return {"seeded": 0, "reason": "hosted inbox present"}
    loader = LoaderAdapter()
    ids = _local_demo_ids(loader)
    if not ids:
        from harbormaster.demo.fixtures import DEMOS

        inbox = data_dir() / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        for email_id, payload in DEMOS.items():
            (inbox / f"{email_id}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ids = list(DEMOS)
    seeded = []
    for email_id in ids:
        try:
            seeded.append(_run_email(email_id, rules_only=True))
        except Exception:
            continue
    return {"seeded": len(seeded), "ids": [r["email_id"] for r in seeded]}


def autoload_official() -> dict:
    """Background-fill missing official emails so the board is never empty."""
    loader = LoaderAdapter()
    official = loader.list_email_ids(source="official")
    if not official:
        return {"ok": False, "reason": "no official inbox"}
    have = {r["email_id"] for r in LedgerStore().list_runs()}
    missing = [eid for eid in official if eid not in have]
    if not missing:
        return {"ok": True, "queued": 0, "have": len(have)}
    job_id = start_corpus_job(
        source="official",
        rules_only=True,
        two_value=False,
        save_board=True,
        degrade=True,
        email_ids=missing,
    )
    return {"ok": True, "job_id": job_id, "queued": len(missing), "have": len(have)}


@router.post("/demo/reset")
def demo_reset():
    store = LedgerStore()
    if store.backend == "postgres" and store.inbox_count():
        return {"written": [], "db_cleared": False, "reason": "hosted ledger is not wiped by Reset"}
    sys.path.insert(0, str(SCRIPTS))
    from demo_reset import reset_demo  # type: ignore

    return reset_demo()


@router.post("/demo/seed")
def demo_seed():
    """Hosted: paint existing ledger, then judge at most one missing email per call."""
    loader = LoaderAdapter()
    store = LedgerStore()
    hosted = _hosted(store)
    if hosted:
        store.purge_demo_runs()
        store.purge_email_prefix("chaos_")
        store.prune_duplicate_runs()
        from harbormaster.ledger.repair import repair_ledger_closures

        repair_ledger_closures(store)
    official = store.list_inbox_ids() or loader.list_email_ids(source="official")
    official = [eid for eid in official if not is_demo_email_id(eid)]
    have_ids = store.list_run_email_ids()
    missing = [eid for eid in official if eid not in have_ids]

    if hosted:
        seeded: list[dict] = []
        for email_id in missing[:SERVERLESS_BATCH]:
            try:
                seeded.append(_run_email(email_id, rules_only=True))
            except Exception:
                break
        return {
            "seeded": seeded,
            "job_id": None,
            "queued": max(0, len(missing) - len(seeded)),
            "official": len(official),
            "have": len(have_ids) + len(seeded),
            "demo": 0,
            "llm_queued": 0,
            "inbox": {"ok": True, "email_count": len(official), "source": "supabase" if store.backend == "postgres" else "local"},
            "reason": "batch" if missing else "hosted ledger already filled",
        }

    sys.path.insert(0, str(SCRIPTS))
    from demo_reset import reset_demo  # type: ignore

    if not store.inbox_count() and not official:
        reset_demo()
    official = loader.list_email_ids(source="official")
    have = store.list_runs()
    have_ids = {r["email_id"] for r in have}
    if official:
        demos: list[str] = []
        rest_source = [eid for eid in official if eid not in have_ids]
        preview = rest_source[:PREVIEW]
        rest = rest_source[PREVIEW:]
    else:
        demos = _local_demo_ids(loader)
        preview = demos[:PREVIEW]
        rest = demos[PREVIEW:]
    results = []
    for email_id in preview:
        try:
            results.append(_run_email(email_id, rules_only=True))
        except Exception:
            continue

    llm_ids = [
        item["email_id"]
        for item in loader.catalog(source="official")
        if item.get("attachments", 0) >= 2 and item["email_id"] not in have_ids
    ]

    job_id = uuid4().hex
    store = LedgerStore()
    total = len(rest) + len(llm_ids)
    store.save_job(job_id, "queued", total, 0)

    def _worker() -> None:
        processed = 0
        job_total = total
        store.save_job(job_id, "running", job_total, 0)
        for email_id in rest:
            try:
                _run_email(email_id, rules_only=True)
            except Exception:
                pass
            processed += 1
            store.save_job(job_id, "running", job_total, processed)
        for email_id in llm_ids:
            try:
                _run_email(email_id, rules_only=False)
            except Exception:
                pass
            processed += 1
            store.save_job(job_id, "running", job_total, processed)
        store.save_job(
            job_id,
            "done",
            job_total,
            processed,
            payload={"official": len(official), "queued": len(rest), "llm": len(llm_ids)},
        )

    threading.Thread(target=_worker, name=f"hm-seed-{job_id[:8]}", daemon=True).start()
    return {
        "seeded": results,
        "job_id": job_id,
        "queued": len(rest),
        "official": len(official),
        "demo": len(demos),
        "llm_queued": len(llm_ids),
        "inbox": loader.health(),
    }
