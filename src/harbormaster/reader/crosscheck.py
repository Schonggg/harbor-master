"""High-risk field dual-path cross-check."""

from __future__ import annotations

from harbormaster.models import FieldValue


def crosscheck(primary: FieldValue, secondary: FieldValue, tol: float = 0.0) -> bool:
    a = " ".join(primary.raw_value.upper().split())
    b = " ".join(secondary.raw_value.upper().split())
    if a == b:
        return True
    if tol > 0 and primary.normalized and secondary.normalized:
        return primary.normalized == secondary.normalized
    return False
