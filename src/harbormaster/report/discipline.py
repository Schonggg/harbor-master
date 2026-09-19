"""Load the score-sheet discipline report for Metrics."""

from __future__ import annotations

import json
from pathlib import Path

from harbormaster.official.matrix import TALKING_POINT

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "reports" / "discipline.json"


def load_discipline_report() -> dict:
    data: dict = {
        "status": "not_run",
        "talking_point": TALKING_POINT,
        "matrix": None,
        "false_alarms": None,
        "ritual": [],
        "note": "Run python scripts/run_discipline.py && python scripts/full_corpus_ritual.py",
    }
    if REPORT.is_file():
        try:
            loaded = json.loads(REPORT.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            data["status"] = "unreadable"
    data.setdefault("talking_point", TALKING_POINT)
    matrix = data.get("matrix") if isinstance(data.get("matrix"), dict) else {}
    traps = data.get("false_alarms") if isinstance(data.get("false_alarms"), dict) else {}
    ritual = data.get("ritual") if isinstance(data.get("ritual"), list) else []
    latest = ritual[-1] if ritual else {}
    cells = int(matrix.get("cells") or 0)
    passed = int(matrix.get("passed") or 0)
    trap_n = traps.get("count")
    ritual_ok = int(latest.get("ok") or 0)
    ritual_n = int(latest.get("count") or 0)
    matrix_ok = cells > 0 and passed == cells and int(matrix.get("fail_count") or 0) == 0
    ritual_clean = bool(latest.get("crash_free")) and ritual_n > 0 and ritual_ok == ritual_n
    if matrix_ok and trap_n == 0 and ritual_clean:
        data["status"] = "ok"
    data["headline"] = {
        "cells": cells,
        "passed": passed,
        "false_alarm_traps": trap_n,
        "ritual_ok": ritual_ok,
        "ritual_count": ritual_n,
        "ritual_kind": latest.get("kind"),
        "status": data.get("status"),
    }
    return data
