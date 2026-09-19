"""Combine per-field court verdicts into has_defect + defect_fields."""

from __future__ import annotations

from harbormaster.models import COMPARE_FIELD_SET, CourtState, FieldName, FieldVerdict, canonical_field_name


def aggregate(verdicts: list[FieldVerdict]) -> tuple[bool, list[str]]:
    defects: list[str] = []
    for fv in verdicts:
        if fv.state != CourtState.MISMATCH:
            continue
        name = canonical_field_name(fv.field)
        if name not in COMPARE_FIELD_SET:
            continue
        if name not in defects:
            defects.append(name)
    order = [f.value for f in FieldName]
    defects.sort(key=lambda n: order.index(n) if n in order else 99)
    return bool(defects), defects
