"""Map port names / aliases to UN/LOCODE for equality."""

from __future__ import annotations

import re

from harbormaster.config import get_locodes
from harbormaster.models import Charge, Plea
from harbormaster.official.compare import CompareOutcome, compare_value, fold

_PORT_FIELDS = {"port_of_loading", "port_of_discharge"}
_PAREN_LOCODE = re.compile(r"\(([A-Z]{5})\)", re.I)
_ANY_PAREN = re.compile(r"\([^)]*\)")


def _fold(value: str) -> str:
    return " ".join(value.upper().replace(".", "").replace(",", " ").split())


def _build_index() -> dict[str, str]:
    index: dict[str, str] = {}

    def add(key: str, locode: str) -> None:
        key = key.strip().upper()
        if not key:
            return
        index[key] = locode
        folded = _fold(key)
        if folded:
            index[folded] = locode

    for row in get_locodes():
        locode = row.locode.upper()
        add(locode, locode)
        add(row.name, locode)
        country = (row.country or "").upper()
        if country:
            add(f"{row.name}, {country}", locode)
            add(f"{row.name} {country}", locode)
        for alias in row.aliases:
            add(alias, locode)
    return index


def resolve_locode(value: str) -> str | None:
    raw = (value or "").strip().upper()
    if not raw:
        return None
    index = _build_index()
    paren = _PAREN_LOCODE.search(raw)
    if paren:
        code = paren.group(1).upper()
        if code in index:
            return index[code]
        return code
    stripped = _ANY_PAREN.sub(" ", raw).strip()
    for key in (raw, stripped, _fold(raw), _fold(stripped)):
        if key in index:
            return index[key]
    head = stripped.split(",")[0].strip()
    if head in index:
        return index[head]
    return index.get(_fold(head))


class LocodeMapStrategy:
    name = "locode_map"

    def try_defend(self, charge: Charge) -> Plea:
        if charge.field not in _PORT_FIELDS:
            return Plea(strategy=self.name, accepted=False, argument="not a port field")
        left_raw = charge.left.raw_value
        right_raw = charge.right.raw_value
        if compare_value(charge.field, left_raw, right_raw) == CompareOutcome.MATCH:
            same = fold(_ANY_PAREN.sub(" ", left_raw))
            return Plea(
                strategy=self.name,
                accepted=True,
                argument="same port after stripping UN/LOCODE parentheses and case",
                transformed_left=same,
                transformed_right=same,
                confidence=1.0,
            )
        left = resolve_locode(left_raw)
        right = resolve_locode(right_raw)
        ok = left is not None and left == right
        return Plea(
            strategy=self.name,
            accepted=ok,
            argument=f"LOCODE resolve: {left} vs {right}",
            transformed_left=left,
            transformed_right=right,
            confidence=1.0 if ok else 0.0,
        )
