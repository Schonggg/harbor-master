from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=1)
def settings() -> dict:
    return {
        "risk_matrix": load_yaml(CONFIG_DIR / "risk_matrix.yaml"),
        "thresholds": load_yaml(CONFIG_DIR / "thresholds.yaml"),
        "field_aliases": load_yaml(CONFIG_DIR / "field_aliases.yaml"),
        "entity_suffixes": load_yaml(CONFIG_DIR / "entity_suffixes.yaml"),
    }
