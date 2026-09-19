"""Resolve referential phrases like SAME AS CONSIGNEE to the actual value."""

from __future__ import annotations

import re

from harbormaster.court.strategies.suffix_strip import normalize_entity
from harbormaster.models import Charge, Plea

_SAME_RE = re.compile(
    r"^\s*(same\s+as\s+(the\s+)?consignee|as\s+consignee|same\s+as\s+above|same)\s*\.?$",
    re.IGNORECASE,
)


def is_same_as_consignee(value: str) -> bool:
    return bool(_SAME_RE.match(value.strip()))


def _consignees_from_note(note: str) -> tuple[str | None, str | None]:
    left = right = None
    for part in note.split("|"):
        part = part.strip()
        if part.startswith("consignee_left="):
            left = part.split("=", 1)[1].strip()
        elif part.startswith("consignee_right="):
            right = part.split("=", 1)[1].strip()
        elif part.startswith("consignee="):
            left = left or part.split("=", 1)[1].strip()
            right = right or left
    return left, right


def resolve_reference(value: str, consignee: str | None) -> str:
    if is_same_as_consignee(value) and consignee:
        return consignee
    return value


class RefResolveStrategy:
    name = "ref_resolve"

    def try_defend(self, charge: Charge) -> Plea:
        left_ref = is_same_as_consignee(charge.left.raw_value)
        right_ref = is_same_as_consignee(charge.right.raw_value)
        cons_left, cons_right = _consignees_from_note(charge.note)

        if left_ref and right_ref:
            return Plea(
                strategy=self.name,
                accepted=True,
                argument="both sides resolve to consignee reference",
                transformed_left="__CONSIGNEE__",
                transformed_right="__CONSIGNEE__",
                confidence=1.0,
            )

        if charge.field == "notify_party" and (left_ref or right_ref):
            left_val = resolve_reference(charge.left.raw_value, cons_left)
            right_val = resolve_reference(charge.right.raw_value, cons_right)
            ok = bool(left_val) and normalize_entity(left_val) == normalize_entity(right_val)
            return Plea(
                strategy=self.name,
                accepted=ok,
                argument=f"resolved notify: '{left_val}' vs '{right_val}'",
                transformed_left=left_val,
                transformed_right=right_val,
                confidence=1.0 if ok else 0.0,
            )
        return Plea(strategy=self.name, accepted=False, argument="no reference pattern")
