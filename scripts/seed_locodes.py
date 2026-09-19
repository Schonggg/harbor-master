#!/usr/bin/env python3
"""Seed / validate locode CSV is readable."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harbormaster.config import clear_caches, get_locodes  # noqa: E402


def main() -> None:
    clear_caches()
    rows = get_locodes()
    print(f"locodes loaded: {len(rows)}")
    assert len(rows) >= 10


if __name__ == "__main__":
    main()
