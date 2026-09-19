"""Handbook L2 scene A, L5 exact compare, L8 assemble, L1 boundary cases."""

from __future__ import annotations

from harbormaster.models import Category, ComparisonStatus, EmailMessage, ReviewReason
from harbormaster.official import assemble
from harbormaster.official.compare import normalize, values_match
from harbormaster.official.gate import claims_attachment_missing, is_placeholder, scene_a_skip_missing_attachment
from harbormaster.reader.health_check import health_check
from harbormaster.scout.rules import official_rule_classify


def test_assemble_assertions_ok_mismatch_review():
    ok = assemble(category=Category.BL_COMPARISON, defect_fields=[])
    assert ok.status == ComparisonStatus.OK
    assert ok.has_defect is False
    assert ok.defect_fields == []
    assert ok.review_reason is None
    assert ok.decided_by == "rule"

    mismatch = assemble(category=Category.BL_COMPARISON, defect_fields=["shipper"])
    assert mismatch.status == ComparisonStatus.MISMATCH
    assert mismatch.has_defect is True
    assert mismatch.defect_fields == ["shipper"]

    review = assemble(
        category=Category.BL_COMPARISON,
        gate_reason=ReviewReason.MISSING_ATTACHMENT,
        defect_fields=["shipper"],
        decided_by="llm",
    )
    assert review.status == ComparisonStatus.NEEDS_REVIEW
    assert review.has_defect is False
    assert review.defect_fields == []
    assert review.review_reason == ReviewReason.MISSING_ATTACHMENT
    assert review.decided_by == "llm"


def test_exact_compare_format_only():
    assert values_match("gross_weight_kg", "1,000 KGS", "1000")
    assert not values_match("gross_weight_kg", "18400", "14800")
    assert values_match("container_count", "6 x 40'HC", "6")
    assert not values_match("container_count", "3", "4")
    assert values_match("shipper", "Acme Trading Co., Ltd.", "ACME TRADING CO LTD")
    assert not values_match("shipper", "ACME TRADING CO LTD", "ACME TRADING INC")
    assert values_match("port_of_loading", "Shanghai (CNSHA)", "shanghai")
    assert not values_match("port_of_loading", "Shanghai", "Ningbo")
    assert normalize("gross_weight_kg", "21.6") == 21


def test_scene_a_please_send_is_not_missing_attachment():
    send = EmailMessage(
        email_id="a1",
        subject="Please send the draft BL",
        body_text="Kindly send the draft BL when ready. Files are not on this mail.",
    )
    assert scene_a_skip_missing_attachment(send) is True
    assert claims_attachment_missing(send) is False
    result = health_check(send, [])
    assert result.ok is True
    assert result.reason is None

    prepare = EmailMessage(
        email_id="a2",
        subject="SI needed",
        body_text="Please prepare the SI for this booking. Files will follow.",
    )
    assert scene_a_skip_missing_attachment(prepare) is True
    assert health_check(prepare, []).ok is True

    provide = EmailMessage(
        email_id="a3",
        subject="Draft BL",
        body_text="Please send us the BL so we can file it.",
    )
    assert scene_a_skip_missing_attachment(provide) is True


def test_compare_but_missing_is_missing_attachment():
    missing = EmailMessage(
        email_id="m1",
        subject="Please confirm the BL",
        body_text="Please compare the draft against the SI. The attachment is still missing.",
    )
    assert scene_a_skip_missing_attachment(missing) is False
    assert claims_attachment_missing(missing) is True
    result = health_check(missing, [])
    assert result.ok is False
    assert result.reason == ReviewReason.MISSING_ATTACHMENT

    dropped = EmailMessage(
        email_id="m2",
        subject="Verify the BL matches the SI",
        body_text="Can you confirm the details? The file dropped and will not open.",
    )
    assert claims_attachment_missing(dropped) is True
    assert health_check(dropped, []).reason == ReviewReason.MISSING_ATTACHMENT

    not_received = EmailMessage(
        email_id="m3",
        subject="Check the draft BL against SI",
        body_text="Please compare — we have not received the attachment yet.",
    )
    assert claims_attachment_missing(not_received) is True


def test_placeholder_is_missing_value():
    assert is_placeholder("???") is True
    assert is_placeholder("TBA") is True
    assert is_placeholder("____") is True
    assert is_placeholder("____MT") is True
    assert is_placeholder("ACME") is False


def test_scout_boundaries():
    invoice = official_rule_classify(
        EmailMessage(
            email_id="b1",
            subject="Booking HM-9 D&D query",
            body_text="This booking has detention / D&D charges on the invoice. Please advise billing.",
        )
    )
    assert invoice and invoice.category == Category.INVOICE_QUERY

    holiday = official_rule_classify(
        EmailMessage(
            email_id="b2",
            subject="Please confirm — season's greetings",
            body_text="Happy holidays from the ops desk. Season's greetings to the team.",
        )
    )
    assert holiday and holiday.category == Category.GENERAL

    business = official_rule_classify(
        EmailMessage(
            email_id="b3",
            subject="Schedule for next week",
            body_text="Can we move the documentation cut-off to Thursday?",
            from_addr="ops@unknown-forwarder.example",
        )
    )
    assert business is None or business.category != Category.SPAM


def test_discipline_report_shows_matrix_ritual_and_zero_traps():
    from harbormaster.report.discipline import load_discipline_report

    data = load_discipline_report()
    head = data["headline"]
    assert head["cells"] == 220
    assert head["passed"] == 220
    assert head["false_alarm_traps"] == 0
    assert head["ritual_count"] == 520
    assert head["ritual_ok"] == 520
    assert data["status"] == "ok"
