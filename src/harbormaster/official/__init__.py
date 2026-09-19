"""L8 assemble — official EmailVerdict with sponsor assertions."""

from __future__ import annotations

from harbormaster.models import (
    COMPARE_FIELD_SET,
    Category,
    ComparisonStatus,
    EmailVerdict,
    ReviewReason,
    ScoutResult,
)


def decided_by_of(scout: ScoutResult | None) -> str:
    if scout and scout.route == "rules":
        return "rule"
    if scout and scout.route == "llm":
        return "llm"
    return "rule"


def assemble(
    *,
    category: Category,
    gate_reason: ReviewReason | None = None,
    defect_fields: list[str] | None = None,
    decided_by: str = "rule",
) -> EmailVerdict:
    """If gate_reason is set, short-circuit to NEEDS_REVIEW. Else OK vs MISMATCH from defects."""
    if category != Category.BL_COMPARISON:
        verdict = EmailVerdict(category=category, decided_by=decided_by)
        _assert_official(verdict)
        return verdict
    if gate_reason is not None:
        verdict = EmailVerdict(
            category=Category.BL_COMPARISON,
            status=ComparisonStatus.NEEDS_REVIEW,
            review_reason=gate_reason,
            decided_by=decided_by,
        )
        _assert_official(verdict)
        return verdict
    defects = [f for f in (defect_fields or []) if f in COMPARE_FIELD_SET]
    if defects:
        verdict = EmailVerdict(
            category=Category.BL_COMPARISON,
            status=ComparisonStatus.MISMATCH,
            has_defect=True,
            defect_fields=defects,
            decided_by=decided_by,
        )
    else:
        verdict = EmailVerdict(
            category=Category.BL_COMPARISON,
            status=ComparisonStatus.OK,
            decided_by=decided_by,
        )
    _assert_official(verdict)
    return verdict


def _assert_official(verdict: EmailVerdict) -> None:
    status = verdict.status.value if verdict.status else None
    assert (status == "MISMATCH") == bool(verdict.defect_fields)
    assert (status == "NEEDS_REVIEW") == (verdict.review_reason is not None)
    assert verdict.has_defect == (status == "MISMATCH")
    assert set(verdict.defect_fields) <= COMPARE_FIELD_SET
