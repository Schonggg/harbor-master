#!/usr/bin/env python3
"""Re-run the sponsor generator on several seeds and score AFTER the pipeline.

Ground truth is read only here. Nothing under src/harbormaster imports it.

    python scripts/calibrate_seeds.py --seeds 7,13,21,42,99
    python3 generate.py --seed 7 --out /tmp/test_seed7
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from harbormaster.graph import nodes  # noqa: E402
from harbormaster.graph.state import PipelineState  # noqa: E402
from harbormaster.ingest.loader_adapter import coerce_email  # noqa: E402
from harbormaster.models import Category, EmailVerdict  # noqa: E402
from harbormaster.report.robustness import TALKING_POINT  # noqa: E402
from harbormaster.report.submission import write_submission  # noqa: E402
from sdoc_paths import find_generator, find_score_cli  # noqa: E402

REPORT = ROOT / "reports" / "seed_robustness.json"


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


def _resolve_attachment(path_str: str, bundle: Path) -> str:
    path = Path(path_str)
    if path.is_file():
        return str(path)
    for root in (bundle, bundle / "inbox", bundle / "attachments"):
        cand = root / path_str
        if cand.is_file():
            return str(cand)
        named = root / Path(path_str).name
        if named.is_file():
            return str(named)
    return path_str


def run_generated_inbox(folder: Path) -> dict[str, EmailVerdict]:
    """Pipeline only. Does not open ground_truth.json."""
    pred: dict[str, EmailVerdict] = {}
    paths = _email_jsons(folder)
    total = len(paths)
    for i, path in enumerate(paths, start=1):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or path.name == "ground_truth.json":
            continue
        email = coerce_email(data, data.get("email_id") or path.stem)
        if not email.email_id:
            continue
        email.attachment_paths = [_resolve_attachment(p, folder) for p in email.attachment_paths]
        for att in email.attachments:
            att.local_path = _resolve_attachment(att.local_path or att.path, folder)
            att.path = att.local_path or att.path
        state = PipelineState(
            email=email,
            degrade=True,
            rules_only=True,
            two_value=True,
            save_board=False,
        )
        for step in (nodes.node_chaos, nodes.node_scout, nodes.node_reader, nodes.node_court):
            state = step(state)
        pred[email.email_id] = state.official or EmailVerdict(category=Category.GENERAL)
        if i == 1 or i % 50 == 0 or i == total:
            print(f"  pipeline {i}/{total}", flush=True)
    return pred


def official_final_score(submission: Path, gold: Path) -> float | None:
    cli = find_score_cli()
    if not cli or not gold.is_file() or not submission.is_file():
        return None
    proc = subprocess.run(
        [sys.executable, str(cli), str(submission), "--ground-truth", str(gold), "--json"],
        cwd=str(cli.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    val = data.get("final_score")
    if val is None:
        return None
    return round(float(val), 4)


def generate_seed(generator: Path, seed: int, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(generator), "--seed", str(seed), "--out", str(out_dir)]
    subprocess.run(cmd, check=True, cwd=str(generator.parent), timeout=600)


def run_local_reproducibility() -> dict[str, Any]:
    """Two rules-only walks of the demo inbox. Does not rewrite data/submission.json."""
    from harbormaster.ingest.loader_adapter import LoaderAdapter

    loader = LoaderAdapter()
    ids = loader.list_email_ids(source="local")
    left: dict[str, dict] = {}
    right: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for email_id in ids:
        try:
            email = loader.load(email_id, source="local")
            state_a = PipelineState(
                email=email.model_copy(deep=True),
                degrade=True,
                rules_only=True,
                two_value=True,
                save_board=False,
            )
            state_b = PipelineState(
                email=email.model_copy(deep=True),
                degrade=True,
                rules_only=True,
                two_value=True,
                save_board=False,
            )
            for step in (nodes.node_chaos, nodes.node_scout, nodes.node_reader, nodes.node_court):
                state_a = step(state_a)
                state_b = step(state_b)
            left[email_id] = (state_a.official or EmailVerdict(category=Category.GENERAL)).as_submission_dict()
            right[email_id] = (state_b.official or EmailVerdict(category=Category.GENERAL)).as_submission_dict()
        except Exception as exc:  # noqa: BLE001
            errors[email_id] = str(exc)
    return {
        "ok": left == right and not errors,
        "count": len(ids),
        "errors": errors,
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
            print(f"seed {seed} -> {dest}", flush=True)
            try:
                generate_seed(generator, seed, dest)
                verdicts = run_generated_inbox(dest)
                pred = {eid: v.as_submission_dict() for eid, v in verdicts.items()}
                gt = _load_gt(dest)
                scored = score_against_gt(pred, gt)
                gold_path = dest / "ground_truth.json"
                if not gold_path.is_file():
                    gold_path = dest / "inbox" / "ground_truth.json"
                sub_path = dest / "submission.json"
                write_submission(verdicts, list(verdicts), sub_path)
                final = official_final_score(sub_path, gold_path)
                seed_rows.append(
                    {
                        "seed": seed,
                        "status": "ok",
                        "emails": len(pred),
                        "final_score": final,
                        **scored,
                    }
                )
                print(
                    f"  seed {seed} exact={scored.get('score_pct')} official={final}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 — report every seed
                seed_rows.append({"seed": seed, "status": "error", "error": str(exc)})
                print(f"  seed {seed} error: {exc}", flush=True)
    local = None if args.skip_local else run_local_reproducibility()
    official_scores = [
        row["final_score"] for row in seed_rows if row.get("final_score") is not None
    ]
    exact_scores = [
        row["score_pct"] / 100.0 for row in seed_rows if row.get("score_pct") is not None
    ]
    variance_values = official_scores or exact_scores
    report = {
        "status": status,
        "talking_point": TALKING_POINT,
        "generator": str(generator) if generator else None,
        "seeds": seed_rows,
        "score_variance": variance(variance_values),
        "score_variance_on": "final_score" if official_scores else "score_pct",
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
