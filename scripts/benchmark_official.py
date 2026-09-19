#!/usr/bin/env python3
"""Run the 520 pipeline and invoke the organizer scorer if it is on disk.

Does not reimplement scoring.py. Set SDOC_DOCKER to the unzipped Docker package.

    py -3 scripts/benchmark_official.py
    py -3 scripts/benchmark_official.py --skip-pipeline
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from harbormaster.graph import nodes  # noqa: E402
from harbormaster.graph.state import PipelineState  # noqa: E402
from harbormaster.ingest.loader_adapter import coerce_email  # noqa: E402
from harbormaster.models import Category, EmailMessage, EmailVerdict  # noqa: E402
from harbormaster.report.official_score import persist_scoreboard  # noqa: E402
from harbormaster.report.submission import write_submission  # noqa: E402
from sdoc_paths import find_gold, find_score_cli, find_scoring  # noqa: E402

BASELINE_FINAL = 0.6429
BASELINE = {
    "stage1_macro_f1": 0.563,
    "stage3_defect_f1": 0.655,
    "end_to_end": 0.652,
    "escalation_precision": 0.066,
    "escalation_recall": 0.750,
    "final_score": BASELINE_FINAL,
}


def _num(board: dict, *keys: str) -> float | None:
    cur: object = board
    for key in keys:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    if isinstance(cur, bool) or cur is None:
        return None
    try:
        return float(cur)
    except (TypeError, ValueError):
        return None


def _pick(board: dict, nested: tuple[str, ...], flat: str) -> float | None:
    return _num(board, *nested) if _num(board, *nested) is not None else _num(board, flat)


def run_scorer(submission: Path) -> dict:
    cli = find_score_cli()
    scoring = find_scoring()
    gold = find_gold()
    if cli:
        cmd = [sys.executable, str(cli), str(submission), "--json"]
        if gold and gold.is_file():
            cmd.extend(["--ground-truth", str(gold)])
        proc = subprocess.run(
            cmd,
            cwd=str(cli.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        board: dict = {
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "returncode": proc.returncode,
            "scorer": str(cli),
        }
        try:
            parsed = json.loads(proc.stdout)
            if isinstance(parsed, dict):
                board.update(parsed)
        except json.JSONDecodeError as exc:
            board["error"] = f"score_cli --json did not parse: {exc}"
        return board
    if scoring and gold:
        sys.path.insert(0, str(scoring.parent))
        import scoring as official_scoring  # type: ignore

        payload = json.loads(submission.read_text(encoding="utf-8"))
        gold_payload = json.loads(gold.read_text(encoding="utf-8"))
        if hasattr(official_scoring, "score"):
            out = official_scoring.score(payload, gold_payload)
        elif hasattr(official_scoring, "score_submission"):
            out = official_scoring.score_submission(payload, gold_payload)
        else:
            raise RuntimeError(f"{scoring} has no score() or score_submission()")
        if not isinstance(out, dict):
            out = {"result": out}
        out["scorer"] = str(scoring)
        return out
    return {
        "error": (
            "Official scorer not found. Unzip sdoc-hackathon-docker next to the repo "
            "or set SDOC_DOCKER / SDOC_GROUND_TRUTH. Pipeline code does not ship gold labels."
        )
    }


def print_summary(board: dict, count: int) -> None:
    final = _pick(board, ("final_score",), "final_score")
    stage1 = _pick(board, ("stage1", "macro_f1"), "stage1_macro_f1")
    stage3 = _pick(board, ("stage3", "defect_f1"), "stage3_defect_f1")
    e2e = _pick(board, ("end_to_end", "rate"), "end_to_end_rate")
    esc_p = _pick(board, ("reliability", "escalation_precision"), "escalation_precision")
    esc_r = _pick(board, ("reliability", "escalation_recall"), "escalation_recall")
    if esc_p is None:
        esc_p = _pick(board, ("reliability", "precision"), "escalation_precision")
    if esc_r is None:
        esc_r = _pick(board, ("reliability", "recall"), "escalation_recall")
    delta = None if final is None else final - BASELINE_FINAL
    print("=" * 50)
    print("HARBOR MASTER OFFICIAL BENCHMARK")
    print("=" * 50)
    print()
    print(f"Emails:                 {count}")
    print()
    print(f"Stage 1 Macro-F1:       {_fmt(stage1)}")
    print(f"Stage 3 Defect F1:      {_fmt(stage3)}")
    print(f"End-to-End:             {_fmt(e2e)}")
    print()
    print(f"Escalation Recall:      {_fmt(esc_r)}")
    print(f"Escalation Precision:   {_fmt(esc_p)}")
    print()
    print(f"FINAL SCORE:            {_fmt(final, 4)}")
    print()
    print(f"Baseline FINAL:         {BASELINE_FINAL:.4f}")
    print(f"Delta:                  {'n/a (scorer missing)' if delta is None else f'{delta:+.4f}'}")
    print("=" * 50)
    if board.get("error"):
        print(board["error"])
    stdout = board.get("stdout")
    if stdout and "SDOC HACKATHON SCORE" in str(stdout):
        print()
        print(stdout)


def _fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _resolve(path_str: str, bundle: Path) -> str:
    path = Path(path_str)
    if path.is_file():
        return str(path)
    inbox = bundle / "inbox"
    for root in (bundle, inbox, inbox.parent):
        cand = root / path_str
        if cand.is_file():
            return str(cand)
        named = root / "attachments" / Path(path_str).name
        if named.is_file():
            return str(named)
    return path_str


def load_local(path: Path, bundle: Path) -> EmailMessage:
    data = json.loads(path.read_text(encoding="utf-8"))
    email = coerce_email(data, email_id=path.stem)
    email.attachment_paths = [_resolve(p, bundle) for p in email.attachment_paths]
    for att in email.attachments:
        att.local_path = _resolve(att.local_path or att.path, bundle)
        att.path = att.local_path or att.path
    return email


def run_local_sdoc() -> tuple[Path, int, dict[str, str]]:
    """Rules-only 520 from data/sdoc — no hosted inbox round-trips."""
    bundle = ROOT / "data" / "sdoc"
    inbox = bundle / "inbox"
    paths = sorted(inbox.glob("email_*.json"))
    if not paths:
        raise FileNotFoundError(f"no emails in {inbox}")
    results: dict[str, EmailVerdict] = {}
    errors: dict[str, str] = {}
    total = len(paths)
    for i, path in enumerate(paths, start=1):
        email_id = path.stem
        try:
            email = load_local(path, bundle)
            state = PipelineState(
                email=email,
                degrade=True,
                rules_only=True,
                two_value=True,
                save_board=False,
            )
            for step in (nodes.node_chaos, nodes.node_scout, nodes.node_reader, nodes.node_court):
                state = step(state)
            assert state.official
            results[email_id] = state.official
        except Exception as exc:  # noqa: BLE001
            errors[email_id] = str(exc)
            results[email_id] = EmailVerdict(category=Category.GENERAL)
        if i == 1 or i % 25 == 0 or i == total:
            print(f"pipeline {i}/{total}", flush=True)
    out_path = ROOT / "data" / "submission.json"
    write_submission(results, [p.stem for p in paths], out_path)
    return out_path, len(results), errors


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-pipeline", action="store_true")
    p.add_argument("--rules-only", action="store_true", default=True)
    args = p.parse_args()

    out_path = ROOT / "data" / "submission.json"
    count = 0
    if args.skip_pipeline and out_path.is_file():
        count = len(json.loads(out_path.read_text(encoding="utf-8")))
        print(f"using existing {out_path} ({count})")
    else:
        out_path, count, errors = run_local_sdoc()
        print(f"wrote {out_path} ({count})")
        if errors:
            print(f"errors {len(errors)}", flush=True)
            for eid, msg in list(errors.items())[:8]:
                print(f"  {eid}: {msg}")

    board = run_scorer(out_path)
    if "error" not in board or board.get("final_score") is not None:
        try:
            persist_scoreboard(board, source="benchmark_official")
        except Exception as exc:
            print(f"could not persist scoreboard: {exc}")
    snap = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "baseline": BASELINE,
        "count": count,
        "submission": str(out_path),
        "scoreboard": board,
        "scorer": str(find_score_cli() or find_scoring() or ""),
        "ground_truth": str(find_gold() or ""),
    }
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "official_benchmark.json").write_text(
        json.dumps(snap, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print_summary(board, count)


if __name__ == "__main__":
    main()
