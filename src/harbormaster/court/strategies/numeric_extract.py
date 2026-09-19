"""Extract leading quantity from packing prose: THREE (3) x 40HC → 3."""

from __future__ import annotations

import re

from harbormaster.models import Charge, Plea

_COUNT_FIELDS = {"container_count", "packages", "quantity", "qty"}

_WORD_NUM = {
    "ZERO": 0,
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
    "NINE": 9,
    "TEN": 10,
    "ELEVEN": 11,
    "TWELVE": 12,
    "TWENTY": 20,
}

_PAREN_NUM = re.compile(r"\(\s*(\d+)\s*\)")
_LEAD_NUM = re.compile(r"^\s*(\d+)")
_WORD_RE = re.compile(
    r"\b(ZERO|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|TWENTY)\b",
    re.IGNORECASE,
)


def extract_count(value: str) -> int | None:
    text = value.strip()
    m = _PAREN_NUM.search(text)
    if m:
        return int(m.group(1))
    m = _LEAD_NUM.match(text)
    if m:
        return int(m.group(1))
    m = _WORD_RE.search(text)
    if m:
        return _WORD_NUM[m.group(1).upper()]
    return None


class NumericExtractStrategy:
    name = "numeric_extract"

    def try_defend(self, charge: Charge) -> Plea:
        if charge.field not in _COUNT_FIELDS and "count" not in charge.field:
            return Plea(strategy=self.name, accepted=False, argument="not a count field")
        left = extract_count(charge.left.raw_value)
        right = extract_count(charge.right.raw_value)
        ok = left is not None and left == right
        return Plea(
            strategy=self.name,
            accepted=ok,
            argument=f"counts: {left} vs {right}",
            transformed_left=None if left is None else str(left),
            transformed_right=None if right is None else str(right),
            confidence=1.0 if ok else 0.0,
        )
