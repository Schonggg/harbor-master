"""Map port names / aliases to UN/LOCODE for equality."""

from __future__ import annotations

from harbormaster.config import get_locodes
from harbormaster.models import Charge, Plea

_PORT_FIELDS = {"port_of_loading", "port_of_discharge"}


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
    raw = value.strip().upper()
    if not raw:
        return None
    index = _build_index()
    if raw in index:
        return index[raw]
    folded = _fold(raw)
    if folded in index:
        return index[folded]
    head = raw.split(",")[0].strip()
    if head in index:
        return index[head]
    return index.get(_fold(head))


class LocodeMapStrategy:
    name = "locode_map"

    def try_defend(self, charge: Charge) -> Plea:
        if charge.field not in _PORT_FIELDS:
            return Plea(strategy=self.name, accepted=False, argument="not a port field")
        left = resolve_locode(charge.left.raw_value)
        right = resolve_locode(charge.right.raw_value)
        ok = left is not None and left == right
        return Plea(
            strategy=self.name,
            accepted=ok,
            argument=f"LOCODE resolve: {left} vs {right}",
            transformed_left=left,
            transformed_right=right,
            confidence=1.0 if ok else 0.0,
        )
