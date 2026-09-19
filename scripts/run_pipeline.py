#!/usr/bin/env python3
"""CLI entry for single-email / demo / full-corpus pipeline runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from harbormaster.graph.pipeline import run_corpus, run_from_request  # noqa: E402
from harbormaster.ingest.loader_adapter import LoaderAdapter  # noqa: E402
from harbormaster.models import RunRequest  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Run Harbormaster pipeline")
    p.add_argument("--email-id", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--degrade", action="store_true")
    p.add_argument("--demo", action="store_true", help="Run demo_si_vs_bl")
    p.add_argument("--full", action="store_true", help="Process every inbox email_id")
    p.add_argument("--rules-only", action="store_true")
    p.add_argument("--submit", action="store_true", help="POST submission.json to inbox /submit")
    p.add_argument("--source", default="auto", choices=["auto", "remote", "local"])
    p.add_argument("--chaos", action="append", default=[])
    args = p.parse_args()

    if args.full:
        out = run_corpus(
            source=args.source,
            rules_only=args.rules_only,
            two_value=True,
            save_board=False,
            degrade=args.degrade or args.rules_only,
        )
        print(json.dumps({k: v for k, v in out.items() if k != "email_ids"}, indent=2, default=str))
        print(f"\n→ wrote {out['path']} ({out['count']} emails)")
        if args.submit:
            loader = LoaderAdapter()
            payload = json.loads(Path(out["path"]).read_text(encoding="utf-8"))
            print(json.dumps(loader.submit(payload), indent=2))
        return

    email_id = "demo_si_vs_bl" if args.demo else args.email_id
    req = RunRequest(
        email_id=email_id,
        dry_run=args.dry_run,
        degrade=args.degrade or args.rules_only,
        chaos=args.chaos,
        rules_only=args.rules_only,
        source=args.source,
    )
    result = run_from_request(req)
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    print(f"\n→ verdict={result.card.verdict.value} case={result.card.case_id}")
    if result.official:
        print(f"→ official={result.official.as_submission_dict()}")


if __name__ == "__main__":
    main()
