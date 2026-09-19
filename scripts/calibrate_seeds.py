#!/usr/bin/env python3
"""Re-run the sponsor generator on several seeds and score AFTER the pipeline.

Ground truth is read only here. Nothing under src/harbormaster imports it.

    python scripts/calibrate_seeds.py --seeds 7,13,21,42,99
    python3 generate.py --seed 7 --out /tmp/test_seed7
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from harbormaster.ingest.loader_adapter import coerce_email  # noqa: E402
from harbormaster.graph.pipeline import run_pipeline  # noqa: E402
from harbormaster.report.robustness import TALKING_POINT  # noqa: E402

REPORT = ROOT / "reports" / "seed_robustness.json"


def find_generator() -> Path | None:
    raw = (os.environ.get("HARBORMASTER_GENERATOR") or "").strip()
    candidates = [
        Path(raw) if raw else None,
        ROOT / "generate.py",
        ROOT / "vendor" / "generate.py",
        Path.home() / "Downloads" / "sdoc-hackathon-bundle" / "generate.py",
        Path.home() / "Downloads" / "generate.py",
    ]
    for path in candidates:
        if path and path.is_file():
            return path
    return None


def unwrap_gt(raw: Any) -> dict[str, dict]:
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get("emails"), dict):
        raw = raw["emails"]
    elif isinstance(raw.get("ground_truth"), dict):
        raw = raw["ground_truth"]
    elif isinstance(raw.get("predictions"), dict):
        raw = raw["predictions"]
    out: dict[str, dict] = {}
    for key, rec in raw.items():
        if isinstance(rec, dict) and (
            "category" in rec or "status" in rec or "has_defect" in rec
        ):
            out[str(key)] = rec
    return out


def score_against_gt(pred: dict[str, dict], gt: dict[str, dict]) -> dict[str, Any]:
    ids = sorted(set(gt) & set(pred))
    if not ids:
        return {"n": 0, "exact": 0, "score_pct": None, "status_match": 0, "category_match": 0}
    exact = status_match = category_match = 0
    for eid in ids:
        g, p = gt[eid], pred[eid]
        if g.get("category") == p.get("category"):
            category_match += 1
        if g.get("status") == p.get("status"):
            status_match += 1
        g_def = set(g.get("defect_fields") or [])
        p_def = set(p.get("defect_fields") or [])
        if (
            g.get("category") == p.get("category")
            and g.get("status") == p.get("status")
            and g.get("review_reason") == p.get("review_reason")
            and bool(g.get("has_defect")) == bool(p.get("has_defect"))
            and g_def == p_def
        ):
            exact += 1
    n = len(ids)
    return {
        "n": n,
        "exact": exact,
        "status_match": status_match,
        "category_match": category_match,
        "score_pct": round(100.0 * exact / n, 2),
        "status_pct": round(100.0 * status_match / n, 2),
        "category_pct": round(100.0 * category_match / n, 2),
    }


def _email_jsons(folder: Path) -> list[Path]:
    skip = {"ground_truth.json", "submission.json", "sample_submission.json"}
    hits: list[Path] = []
    for name in ("inbox", "emails", "."):
        base = folder if name == "." else folder / name
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.json")):
            if path.name in skip:
                continue
            hits.append(path)
        if hits and name != ".":
            break
    return hits


def _load_gt(folder: Path) -> dict[str, dict]:
    for path in (
        folder / "ground_truth.json",
        folder / "inbox" / "ground_truth.json",
        folder / "emails" / "ground_truth.json",
    ):
        if path.is_file():
            return unwrap_gt(json.loads(path.read_text(encoding="utf-8")))
    return {}


def run_generated_inbox(folder: Path) -> dict[str, dict]:
    """Pipeline only. Does not open ground_truth.json."""
    pred: dict[str, dict] = {}
    for path in _email_jsons(folder):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        if path.name == "ground_truth.json":
            continue
        email = coerce_email(data, data.get("email_id") or path.stem)
        if not email.email_id:
            continue
        result = run_pipeline(
            email,
            degrade=True,
            rules_only=True,
            two_value=True,
            save_board=False,
        )
        if result.official:
            pred[email.email_id] = result.official.as_submission_dict()
    return pred


def generate_seed(generator: Path, seed: int, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(generator), "--seed", str(seed), "--out", str(out_dir)]
    subprocess.run(cmd, check=True, cwd=str(generator.parent), timeout=180)


def run_local_reproducibility() -> dict[str, Any]:
    from harbormaster.graph.pipeline import run_corpus

    a = run_corpus(source="local", rules_only=True, two_value=True, save_board=False)
    b = run_corpus(source="local", rules_only=True, two_value=True, save_board=False)
    left = json.loads(Path(a["path"]).read_text(encoding="utf-8"))
    right = json.loads(Path(b["path"]).read_text(encoding="utf-8"))
    return {
        "ok": left == right,
        "count": a["count"],
        "errors": a.get("errors") or {},
    }


def variance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return round(statistics.pstdev(values), 3)


def main() -> None:
    p = argparse.ArgumentParser(description="Multi-seed generator robustness (GT only in this harness)")
    p.add_argument("--seeds", default="7,13,21,42,99")
    p.add_argument("--out", default=str(ROOT / "reports" / "seed_runs"))
    p.add_argument("--skip-local", action="store_true")
    args = p.parse_args()
    seeds = [int(x.strip()) for x in str(args.seeds).split(",") if x.strip()]
    generator = find_generator()
    seed_rows: list[dict[str, Any]] = []
    status = "generator_not_in_tree"
    note = (
        "generate.py was not found. Set HARBORMASTER_GENERATOR or drop it next to the repo. "
        "Local demo corpus still checks that two rules-only runs are identical."
    )
    if generator:
        status = "ok"
        note = f"Generator {generator}. Pipeline never imported ground_truth.json."
        work = Path(args.out)
        for seed in seeds:
            dest = work / f"seed_{seed}"
            try:
                generate_seed(generator, seed, dest)
                pred = run_generated_inbox(dest)
                gt = _load_gt(dest)
                scored = score_against_gt(pred, gt)
                seed_rows.append({"seed": seed, "status": "ok", "emails": len(pred), **scored})
            except Exception as exc:  # noqa: BLE001 — report every seed
                seed_rows.append({"seed": seed, "status": "error", "error": str(exc)})
    local = None if args.skip_local else run_local_reproducibility()
    scores = [row["score_pct"] for row in seed_rows if row.get("score_pct") is not None]
    report = {
        "status": status,
        "talking_point": TALKING_POINT,
        "generator": str(generator) if generator else None,
        "seeds": seed_rows,
        "score_variance": variance(scores),
        "local_reproducibility": local,
        "note": note,
        "command": "python3 generate.py --seed 7 --out /tmp/test_seed7",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n-> wrote {REPORT}")


if __name__ == "__main__":
    main()
