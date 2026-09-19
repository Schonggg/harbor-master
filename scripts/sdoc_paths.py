"""Locate the organizer Docker scorer. Not imported by src/harbormaster."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD_FILENAME = "ground_truth.json"


def scorer_roots() -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("SDOC_DOCKER") or os.environ.get("SDOC_SCORER_DIR") or ""
    if env:
        roots.append(Path(env))
    roots.extend(
        [
            ROOT / "sdoc-hackathon-docker",
            ROOT.parent / "sdoc-hackathon-docker",
            Path(r"D:\Downloads\sdoc-hackathon-docker"),
            Path.home() / "Downloads" / "sdoc-hackathon-docker",
            Path(r"D:\Downloads\sdoc-hackathon-bundle"),
        ]
    )
    seen: list[Path] = []
    for path in roots:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.append(resolved)
    return seen


def find_file(name: str) -> Path | None:
    for root in scorer_roots():
        if not root.exists():
            continue
        for folder in ("", "server", "scorer", "eval"):
            cand = (root / folder / name) if folder else (root / name)
            if cand.is_file():
                return cand
        for hit in root.glob(f"*/{name}"):
            if hit.is_file():
                return hit
    return None


def find_score_cli() -> Path | None:
    return find_file("score_cli.py")


def find_scoring() -> Path | None:
    return find_file("scoring.py")


def find_gold() -> Path | None:
    env = os.environ.get("SDOC_GROUND_TRUTH") or os.environ.get("SDOC_GOLD") or ""
    if env:
        path = Path(env)
        if path.is_file():
            return path
    return find_file(GOLD_FILENAME)
