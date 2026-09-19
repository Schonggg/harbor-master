"""Copy the Bridge into public/ so Vercel serves it from the CDN."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web"
DEST = ROOT / "public"


def main() -> None:
    if not (SRC / "index.html").is_file():
        raise SystemExit(f"missing Bridge UI at {SRC}")
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(SRC, DEST, ignore=shutil.ignore_patterns(".*"))
    print(f"copied {SRC} -> {DEST}")


if __name__ == "__main__":
    main()
