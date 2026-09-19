"""Each of the four NEEDS_REVIEW triggers."""

from __future__ import annotations

from harbormaster.models import EmailMessage, ExtractedDocument, FieldValue, ReviewReason
from harbormaster.reader.health_check import health_check


def _fv(name: str, value: str) -> FieldValue:
    return FieldValue(name=name, raw_value=value, confidence=0.95)


def _full_fields() -> dict[str, FieldValue]:
    return {
        "shipper": _fv("shipper", "ACME"),
        "consignee": _fv("consignee", "BETA"),
        "notify_party": _fv("notify_party", "SAME AS CONSIGNEE"),
        "port_of_loading": _fv("port_of_loading", "Shanghai"),
        "port_of_discharge": _fv("port_of_discharge", "Los Angeles"),
        "container_count": _fv("container_count", "3"),
        "gross_weight_kg": _fv("gross_weight_kg", "1000 KGS"),
    }


def test_missing_attachment():
    email = EmailMessage(email_id="e1", subject="please check BL draft vs SI")
    result = health_check(email, [])
    assert result.ok is False
    assert result.reason == ReviewReason.MISSING_ATTACHMENT


def test_unreadable():
    email = EmailMessage(email_id="e1", subject="SI vs BL", attachment_paths=["si.pdf", "bl.pdf"])
    si = ExtractedDocument(filename="si.pdf", kind="si", text="", parser_used="vision")
    bl = ExtractedDocument(filename="bl.pdf", kind="bl", text="", parser_used="vision")
    result = health_check(email, [si, bl], si=si, bl=bl)
    assert result.ok is False
    assert result.reason == ReviewReason.UNREADABLE


def test_wrong_doc_type():
    email = EmailMessage(email_id="e1", subject="SI vs BL", attachment_paths=["inv.pdf", "pl.pdf"])
    fields = _full_fields()
    si = ExtractedDocument(
        filename="commercial_invoice.pdf",
        kind="other",
        text="COMMERCIAL INVOICE\n" + "x" * 80,
        fields=fields,
    )
    bl = ExtractedDocument(
        filename="packing_list.pdf",
        kind="other",
        text="PACKING LIST\n" + "x" * 80,
        fields=fields,
    )
    result = health_check(email, [si, bl], si=si, bl=bl)
    assert result.ok is False
    assert result.reason == ReviewReason.WRONG_DOC_TYPE


def test_missing_value():
    email = EmailMessage(email_id="e1", subject="SI vs BL", attachment_paths=["si.txt", "bl.txt"])
    fields = _full_fields()
    si_fields = dict(fields)
    si_fields.pop("shipper")
    si = ExtractedDocument(
        filename="si.txt",
        kind="si",
        text="SHIPPING INSTRUCTION\nConsignee: BETA\n" + "x" * 80,
        fields=si_fields,
    )
    bl = ExtractedDocument(
        filename="bl.txt",
        kind="bl",
        text="BILL OF LADING\nConsignee: BETA\n" + "x" * 80,
        fields=fields,
    )
    result = health_check(email, [si, bl], si=si, bl=bl)
    assert result.ok is False
    assert result.reason == ReviewReason.MISSING_VALUE
    assert "shipper" in result.missing_fields


def test_healthy_pair_passes():
    email = EmailMessage(email_id="e1", subject="SI vs BL", attachment_paths=["si.txt", "bl.txt"])
    fields = _full_fields()
    si = ExtractedDocument(
        filename="si.txt",
        kind="si",
        text="SHIPPING INSTRUCTION\n" + "x" * 80,
        fields=fields,
    )
    bl = ExtractedDocument(
        filename="bl.txt",
        kind="bl",
        text="BILL OF LADING\n" + "x" * 80,
        fields=fields,
    )
    result = health_check(email, [si, bl], si=si, bl=bl)
    assert result.ok is True
    assert result.reason is None
