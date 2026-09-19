"""Strip corporate suffixes and punctuation for entity equality."""

from __future__ import annotations

import re

from harbormaster.config import get_entity_suffixes
from harbormaster.models import Charge, Plea


def _soft_suffix(suf: str) -> str:
    soft = re.sub(r"[^\w\s]", " ", suf.upper())
    return re.sub(r"\s+", " ", soft).strip()


def normalize_entity(value: str) -> str:
    cfg = get_entity_suffixes()
    text = value.upper().strip()
    if cfg.normalize_ampersand:
        text = text.replace("&", " AND ")

    # Pass 1: strip suffixes while punctuation still present ("CO., LTD.")
    changed = True
    while changed:
        changed = False
        for suf in cfg.suffixes:
            pattern = rf"\b{re.escape(suf.upper())}\s*$"
            new = re.sub(pattern, "", text).strip()
            if new != text:
                text = new
                changed = True

    for ch in cfg.strip_chars:
        text = text.replace(ch, " ")
    text = re.sub(r"\s+", " ", text).strip()

    # Pass 2: strip punctuation-normalized suffixes ("CO LTD", "INC")
    changed = True
    while changed:
        changed = False
        for suf in cfg.suffixes:
            soft = _soft_suffix(suf)
            if not soft:
                continue
            pattern = rf"\b{re.escape(soft)}\s*$"
            new = re.sub(pattern, "", text).strip()
            if new != text:
                text = new
                changed = True
        text = re.sub(r"\s+", " ", text).strip()
    return text


class SuffixStripStrategy:
    name = "suffix_strip"

    def try_defend(self, charge: Charge) -> Plea:
        left = normalize_entity(charge.left.raw_value)
        right = normalize_entity(charge.right.raw_value)
        ok = bool(left) and left == right
        return Plea(
            strategy=self.name,
            accepted=ok,
            argument=f"Normalized entities: '{left}' vs '{right}'",
            transformed_left=left,
            transformed_right=right,
            confidence=1.0 if ok else 0.0,
        )
