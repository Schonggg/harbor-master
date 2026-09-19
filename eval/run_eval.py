"""Eval runner — score inbox runs and snapshot results."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harbormaster.graph.pipeline import run_from_request  # noqa: E402
from harbormaster.ingest.loader_adapter import LoaderAdapter  # noqa: E402
from harbormaster.models import RunRequest  # noqa: E402


def main() -> None:
    loader = LoaderAdapter()
    ids = loader.list_email_ids()
    rows = []
    for email_id in ids:
        result = run_from_request(RunRequest(email_id=email_id, degrade=True))
        rows.append(
            {
                "email_id": email_id,
                "verdict": result.card.verdict.value,
                "fields": [
                    {"name": fv.field, "state": fv.state.value, "strategy": fv.winning_strategy}
                    for fv in result.card.field_verdicts
                ],
            }
        )
    snap_dir = ROOT / "eval" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = snap_dir / f"eval_{stamp}.json"
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"wrote {path} ({len(rows)} emails)")


if __name__ == "__main__":
    main()
