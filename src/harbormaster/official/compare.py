"""L5 exact comparison — format normalize only, no fuzzy / no third state.

A miss can still leave a record standing. A false alarm zeros it.
Every new normalize rule must keep EQUIVALENT pairs matching in official.matrix.
"""

from __future__ import annotations

import re

from harbormaster.models import COMPARE_FIELDS

_WEIGHT = re.compile(r"[\d,.]+")
_COUNT = re.compile(r"(\d+)")
_LOCODE = re.compile(r"\([^)]*\)")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def fold(text: str) -> str:
    raw = (text or "").casefold()
    raw = _PUNCT.sub(" ", raw)
    return " ".join(raw.split())


def normalize(field: str, raw: str) -> str | int | None:
    text = (raw or "").strip()
    if not text:
        return None
    if field == "gross_weight_kg":
        hit = _WEIGHT.search(text.replace(",", ""))
        if not hit:
            return None
        try:
            return int(float(hit.group(0)))
        except ValueError:
            return None
    if field == "container_count":
        hit = _COUNT.search(text)
        if not hit:
            return None
        return int(hit.group(1))
    if field in {"port_of_loading", "port_of_discharge"}:
        return fold(_LOCODE.sub(" ", text))
    if field in {"shipper", "consignee", "notify_party"}:
        return fold(text)
    return fold(text)


def values_match(field: str, left: str, right: str) -> bool:
    a = normalize(field, left)
    b = normalize(field, right)
    if a is None or b is None:
        return False
    return a == b


def exact_defect_fields(pairs: dict[str, tuple[str, str]]) -> list[str]:
    defects: list[str] = []
    for field in COMPARE_FIELDS:
        if field not in pairs:
            continue
        left, right = pairs[field]
        if not values_match(field, left, right):
            defects.append(field)
    return defects
