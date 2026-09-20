"""L5 exact comparison - format normalize only, no fuzzy matching.

A miss can still leave a record standing. A false alarm zeros it.
Every new normalize rule must keep EQUIVALENT pairs matching in official.matrix.

UNPARSEABLE is not a third match state. It means normalize() could not read a
value, so the official path must not emit MISMATCH (that would be a false alarm).
"""

from __future__ import annotations

import re
from enum import Enum

from harbormaster.models import COMPARE_FIELDS

_WEIGHT = re.compile(r"[\d,.]+")
_COUNT = re.compile(r"(\d+)")
_LOCODE = re.compile(r"\([^)]*\)")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_PARTY_PREFIX = re.compile(
    r"^(?:party/?\s*intermediate\s*consignee(?:\s*\([^)]*\))?|"
    r"\(?non[-\s]?negotiable\)?|"
    r"(?:notify(?:\s+party)?|consignee|shipper)\s*:)\s*:?\s*",
    re.I,
)
_PIPE_TAIL = re.compile(r"\s*\|.*$", re.S)


class CompareOutcome(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNPARSEABLE = "unparseable"


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
        text = _PARTY_PREFIX.sub("", text).strip()
        text = _PIPE_TAIL.sub("", text).strip()
        return fold(text)
    return fold(text)


def compare_value(field: str, left: str, right: str) -> CompareOutcome:
    """Exact compare after format normalize. None from normalize is UNPARSEABLE."""
    a = normalize(field, left)
    b = normalize(field, right)
    if a is None or b is None:
        return CompareOutcome.UNPARSEABLE
    return CompareOutcome.MATCH if a == b else CompareOutcome.MISMATCH


def values_match(field: str, left: str, right: str) -> bool:
    """Boolean wrapper for format-matrix / EQUIVALENT cells.

    Deprecated for official assemble. New code should call compare_value().
    UNPARSEABLE returns False here so matrix callers keep a bool; it must not
    be treated as an official MISMATCH (see exact_defect_fields).
    """
    return compare_value(field, left, right) == CompareOutcome.MATCH


def exact_defect_fields(pairs: dict[str, tuple[str, str]]) -> tuple[list[str], list[str]]:
    """Return (confirmed defect fields, fields that could not be parsed)."""
    defects: list[str] = []
    unparseable: list[str] = []
    for field in COMPARE_FIELDS:
        if field not in pairs:
            continue
        left, right = pairs[field]
        outcome = compare_value(field, left, right)
        if outcome == CompareOutcome.MISMATCH:
            defects.append(field)
        elif outcome == CompareOutcome.UNPARSEABLE:
            unparseable.append(field)
    return defects, unparseable
