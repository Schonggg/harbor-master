#!/usr/bin/env python3
"""Tick every field x format x label cell. Write reports/discipline.json."""

from __future__ import annotations

import json
import os
import sys
import tempfile
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

from harbormaster.official.matrix import TALKING_POINT, false_alarm_pairs, run_matrix  # noqa: E402
from harbormaster.report.discipline import REPORT  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hm-matrix-") as raw:
        matrix = run_matrix(Path(raw))
    alarms = false_alarm_pairs()
    false_n = sum(1 for r in alarms if r["false_alarm"])
    existing = {}
    if REPORT.is_file():
        try:
            existing = json.loads(REPORT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    report = {
        "status": "ok" if not matrix["failed"] and false_n == 0 else "failed",
        "talking_point": TALKING_POINT,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "matrix": {
            "cells": matrix["cells"],
            "passed": matrix["passed"],
            "fail_count": len(matrix["failed"]),
            "failed": matrix["failed"][:20],
            "by_fmt": matrix["by_fmt"],
            "by_field": matrix["by_field"],
            "grid": matrix["grid"],
            "formats": matrix["formats"],
            "fields": matrix["fields"],
        },
        "false_alarms": {
            "count": false_n,
            "pairs": alarms,
        },
        "ritual": existing.get("ritual") or [],
        "note": "Every cell is extract + exact compare. Equivalent pairs must never defect.",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": report["status"], "cells": matrix["cells"], "passed": matrix["passed"], "false_alarms": false_n}, indent=2))
    print(f"-> wrote {REPORT}")
    if report["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
