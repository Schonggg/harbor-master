from __future__ import annotations

from harbormaster.models import Category, ComparisonStatus, EmailVerdict


def test_non_bl_categories_default_status_ok():
    for category in (
        Category.GENERAL,
        Category.SPAM,
        Category.SI_REQUEST,
        Category.INVOICE_QUERY,
    ):
        rec = EmailVerdict(category=category).as_submission_dict()
        assert rec["status"] == "OK", category
        assert rec["review_reason"] is None
        assert rec["has_defect"] is False
        assert rec["defect_fields"] == []


def test_bl_mismatch_status_is_preserved():
    rec = EmailVerdict(
        category=Category.BL_COMPARISON,
        status=ComparisonStatus.MISMATCH,
        defect_fields=["consignee"],
    ).as_submission_dict()
    assert rec["status"] == "MISMATCH"
    assert rec["has_defect"] is True
    assert rec["defect_fields"] == ["consignee"]
