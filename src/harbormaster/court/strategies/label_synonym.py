"""Treat known label synonyms as the same semantic field value.

For court charges the field name is already canonical; this strategy
normalizes alias-like *values* that are really labels (e.g. 'POL' vs
'Port of Loading' appearing as values in free text compare edge cases).
Primary use: if raw values are alias strings of the same canonical field
label, accept as match (rare). More commonly used by scout/reader; kept
here so the seven-strategy demo path is complete.
"""

from __future__ import annotations

from harbormaster.config import get_field_aliases
from harbormaster.models import Charge, Plea


def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, aliases in get_field_aliases().items():
        index[canonical.upper()] = canonical
        for a in aliases:
            index[a.upper()] = canonical
    return index


def canonical_label(value: str) -> str | None:
    return _alias_index().get(value.strip().upper())


class LabelSynonymStrategy:
    name = "label_synonym"

    def try_defend(self, charge: Charge) -> Plea:
        left = canonical_label(charge.left.raw_value)
        right = canonical_label(charge.right.raw_value)
        if left and right and left == right:
            return Plea(
                strategy=self.name,
                accepted=True,
                argument=f"label aliases both map to {left}",
                transformed_left=left,
                transformed_right=right,
                confidence=1.0,
            )
        # Soft path: casefold + whitespace collapse equality for near-labels
        def soft(s: str) -> str:
            return " ".join(s.upper().split())

        ok = soft(charge.left.raw_value) == soft(charge.right.raw_value)
        return Plea(
            strategy=self.name,
            accepted=ok,
            argument="soft label normalize" if ok else "no synonym hit",
            transformed_left=soft(charge.left.raw_value),
            transformed_right=soft(charge.right.raw_value),
            confidence=0.8 if ok else 0.0,
        )
