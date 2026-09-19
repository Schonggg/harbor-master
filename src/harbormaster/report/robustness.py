"""Load the seed-robustness report for Metrics. Never reads ground_truth into the pipeline."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "reports" / "seed_robustness.json"

TALKING_POINT = (
    "We do not memorize one frozen inbox. Given the sponsor generator we re-run "
    "python3 generate.py --seed N --out <dir> and score each corpus after the pipeline, "
    "never importing ground_truth.json into scoring code paths."
)


def load_robustness_report() -> dict:
    data: dict = {
        "status": "not_run",
        "talking_point": TALKING_POINT,
        "seeds": [],
        "score_variance": None,
        "local_reproducibility": None,
        "note": "Run python scripts/calibrate_seeds.py --seeds 7,13,21,42,99",
    }
    if REPORT.is_file():
        try:
            loaded = json.loads(REPORT.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            data["status"] = "unreadable"
    data.setdefault("talking_point", TALKING_POINT)
    return data
