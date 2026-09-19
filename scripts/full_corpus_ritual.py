#!/usr/bin/env python3
"""Full official inbox, twice a day. Never writes the hosted ledger."""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["DATABASE_URL"] = ""

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
os.environ["DATABASE_URL"] = ""

from harbormaster.config import clear_caches  # noqa: E402

clear_caches()

from harbormaster.graph.pipeline import run_pipeline  # noqa: E402
from harbormaster.ingest.loader_adapter import LoaderAdapter  # noqa: E402
from harbormaster.report.discipline import REPORT  # noqa: E402


def _stamp(kind: str) -> dict:
    loader = LoaderAdapter()
    ids = loader.required_email_ids(source="official") or loader.list_email_ids(source="local")
    errors: dict[str, str] = {}
    ok = 0
    for email_id in ids:
        try:
            email = loader.load(email_id)
            run_pipeline(
                email,
                degrade=True,
                rules_only=True,
                two_value=True,
                save_board=False,
            )
            ok += 1
            if ok % 50 == 0:
                print(f"{ok}/{len(ids)}", flush=True)
        except Exception as exc:  # noqa: BLE001 — ritual must record every crash
            errors[email_id] = f"{exc}\n{traceback.format_exc(limit=2)}"
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "count": len(ids),
        "ok": ok,
        "crash_free": not errors,
        "errors": {k: v[:400] for k, v in list(errors.items())[:12]},
        "error_count": len(errors),
    }


def main() -> None:
    kind = "evening" if len(sys.argv) < 2 else sys.argv[1]
    row = _stamp(kind)
    existing: dict = {}
    if REPORT.is_file():
        try:
            existing = json.loads(REPORT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    ritual = list(existing.get("ritual") or [])
    ritual.append(row)
    existing["ritual"] = ritual[-8:]
    if row["crash_free"]:
        existing["status"] = "ok"
    else:
        existing["status"] = "failed"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: row[k] for k in ("at", "kind", "count", "ok", "crash_free", "error_count")}, indent=2))
    print(f"-> wrote {REPORT}")
    if not row["crash_free"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
