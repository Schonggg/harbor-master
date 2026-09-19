#!/usr/bin/env python3
"""Pretty-print the latest organizer scoreboard saved under reports/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from harbormaster.report.official_score import format_report  # noqa: E402


def main() -> None:
    sys.stdout.write(format_report())


if __name__ == "__main__":
    main()
