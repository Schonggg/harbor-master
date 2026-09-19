#!/usr/bin/env python3
"""Copy the SQLite ledger to data/backups/."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from harbormaster.config import data_dir  # noqa: E402
from harbormaster.ledger.store import LedgerStore  # noqa: E402


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = data_dir() / "backups" / f"harbormaster-{stamp}.db"
    path = LedgerStore().backup(dest)
    print(path)


if __name__ == "__main__":
    main()
