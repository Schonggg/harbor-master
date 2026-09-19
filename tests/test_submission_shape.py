"""Guard official submission shape against the sponsor schema."""

from __future__ import annotations

import pytest

from harbormaster.models import (
    Category,
    CaseCard,
    CaseVerdict,
    ComparisonStatus,
    EmailMessage,
    EmailVerdict,
    FieldName,
    ReviewReason,
    Submission,
)
from harbormaster.report.submission import (
    build_bridge_submission,
    build_submission,
    validate_submission,
)


REQUIRED_EMAIL_KEYS = {"category", "status", "review_reason", "has_defect", "defect_fields", "decided_by"}
CATEGORIES = {c.value for c in Category}
STATUSES = {s.value for s in ComparisonStatus}
REASONS = {r.value for r in ReviewReason}
FIELDS = {f.value for f in FieldName}


def test_bridge_payload_still_has_verdict():
    email = EmailMessage(email_id="e1", subject="SI vs BL")
    card = CaseCard(email_id="e1", subject="SI vs BL", verdict=CaseVerdict.CLEAR)
    sub = build_bridge_submission(email, card)
    assert {"schema_version", "email_id", "case_id", "verdict", "fields"} <= set(sub)
    assert sub["verdict"] in {"CLEAR", "HOLD", "PILOT"}


def test_official_per_email_shape():
    email = EmailMessage(email_id="e1", subject="hello")
    card = CaseCard(email_id="e1", subject="hello", verdict=CaseVerdict.CLEAR)
    rec = build_submission(email, card)
    assert set(rec) == REQUIRED_EMAIL_KEYS
    assert rec["category"] in CATEGORIES
    assert rec["status"] in STATUSES
    assert rec["review_reason"] in REASONS | {None}
    assert rec["has_defect"] is False
    assert rec["defect_fields"] == []


def test_coverage_rejects_missing_ids():
    payload = {
        "1": EmailVerdict(category=Category.GENERAL).as_submission_dict(),
        "2": EmailVerdict(category=Category.SPAM).as_submission_dict(),
    }
    with pytest.raises(ValueError, match="missing"):
        validate_submission(payload, ["1", "2", "3"])


def test_coverage_rejects_extra_ids():
    payload = {
        "1": EmailVerdict(category=Category.GENERAL).as_submission_dict(),
        "x": EmailVerdict(category=Category.GENERAL).as_submission_dict(),
    }
    with pytest.raises(ValueError, match="unexpected"):
        validate_submission(payload, ["1"])


def test_bl_mismatch_populates_defect_fields():
    rec = EmailVerdict(
        category=Category.BL_COMPARISON,
        status=ComparisonStatus.MISMATCH,
        defect_fields=["shipper", "gross_weight_kg"],
    )
    data = rec.as_submission_dict()
    assert data["has_defect"] is True
    assert data["defect_fields"] == ["shipper", "gross_weight_kg"]
    assert data["review_reason"] is None
    assert set(data["defect_fields"]) <= FIELDS


def test_needs_review_clears_defects():
    rec = EmailVerdict(
        category=Category.BL_COMPARISON,
        status=ComparisonStatus.NEEDS_REVIEW,
        review_reason=ReviewReason.MISSING_ATTACHMENT,
        has_defect=True,
        defect_fields=["shipper"],
    )
    data = rec.as_submission_dict()
    assert data["has_defect"] is False
    assert data["defect_fields"] == []
    assert data["review_reason"] == "missing_attachment"


def test_submission_root_covers_all():
    ids = [str(i) for i in range(12)]
    root = {i: EmailVerdict(category=Category.GENERAL) for i in ids}
    sub = Submission(root)
    sub.validate_coverage(ids)
    dumped = sub.as_dict()
    assert set(dumped) == set(ids)
    for rec in dumped.values():
        assert set(rec) == REQUIRED_EMAIL_KEYS
