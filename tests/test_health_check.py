"""Each of the four NEEDS_REVIEW triggers."""

from __future__ import annotations

from harbormaster.models import EmailMessage, ExtractedDocument, FieldValue, ReviewReason
from harbormaster.reader.health_check import classify_doc_kind, health_check


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


def _invoice_body() -> str:
    return "\n".join(
        [
            "Item  Qty  Line total",
            "Paper  10  $120.00",
            "Board  20  $240.00",
            "Pulp   5   USD 80.50",
            "Tax    1   $12.00",
        ]
    )


def _packing_body() -> str:
    return "\n".join(
        [
            "Pieces by carton",
            "CTN-01 paper reams",
            "CTN-02 paper reams",
            "CTN-03 pulp sheets",
            "CARTON NO. 4 mixed",
        ]
    )


def test_invoice_structure_without_keywords_is_wrong_doc_type():
    inv = ExtractedDocument(filename="charges.pdf", text=_invoice_body(), fields={})
    assert classify_doc_kind(inv) == "other"
    email = EmailMessage(email_id="e1", subject="SI vs BL", attachment_paths=["si.txt", "charges.pdf"])
    fields = _full_fields()
    si = ExtractedDocument(
        filename="si.txt",
        kind="si",
        text="SHIPPING INSTRUCTION\n" + "x" * 80,
        fields=fields,
    )
    inv.kind = classify_doc_kind(inv)
    result = health_check(email, [si, inv], si=si, bl=inv)
    assert result.ok is False
    assert result.reason == ReviewReason.WRONG_DOC_TYPE


def test_packing_structure_without_keywords_is_wrong_doc_type():
    pl = ExtractedDocument(filename="cartons.pdf", text=_packing_body(), fields={})
    assert classify_doc_kind(pl) == "other"
    email = EmailMessage(email_id="e1", subject="SI vs BL", attachment_paths=["si.txt", "cartons.pdf"])
    fields = _full_fields()
    si = ExtractedDocument(
        filename="si.txt",
        kind="si",
        text="SHIPPING INSTRUCTION\n" + "x" * 80,
        fields=fields,
    )
    pl.kind = classify_doc_kind(pl)
    result = health_check(email, [si, pl], si=si, bl=pl)
    assert result.ok is False
    assert result.reason == ReviewReason.WRONG_DOC_TYPE


def test_normal_bl_is_not_structurally_wrong():
    fields = _full_fields()
    bl = ExtractedDocument(
        filename="bl.txt",
        text="BILL OF LADING\nPort of loading Shanghai\n3 x 40HC\n" + "x" * 80,
        fields=fields,
    )
    assert classify_doc_kind(bl) == "bl"


def test_normal_si_is_not_structurally_wrong():
    fields = _full_fields()
    si = ExtractedDocument(
        filename="si.txt",
        text="SHIPPING INSTRUCTION\nShipper ACME\nConsignee BETA\n" + "x" * 80,
        fields=fields,
    )
    assert classify_doc_kind(si) == "si"


def test_ocr_failed_bl_is_not_wrong_doc_type():
    noise = ("scan noise ## " * 40).strip()
    bl = ExtractedDocument(filename="scan.pdf", text=noise, fields={})
    assert classify_doc_kind(bl) == "unknown"
    email = EmailMessage(email_id="e1", subject="SI vs BL", attachment_paths=["si.txt", "scan.pdf"])
    si = ExtractedDocument(
        filename="si.txt",
        kind="si",
        text="SHIPPING INSTRUCTION\n" + "x" * 80,
        fields=_full_fields(),
    )
    result = health_check(email, [si, bl], si=si, bl=bl)
    assert result.reason != ReviewReason.WRONG_DOC_TYPE


def test_garbage_content_does_not_crash():
    junk = ExtractedDocument(filename="a.txt", text=("xyz " * 40).strip(), fields={})
    junk2 = ExtractedDocument(filename="b.txt", text=("qwe " * 40).strip(), fields={})
    email = EmailMessage(email_id="e1", subject="SI vs BL", attachment_paths=["a.txt", "b.txt"])
    result = health_check(email, [junk, junk2])
    assert result.reason != ReviewReason.WRONG_DOC_TYPE
    assert result.reason in {
        None,
        ReviewReason.MISSING_VALUE,
        ReviewReason.UNREADABLE,
        ReviewReason.MISSING_ATTACHMENT,
    }


def test_priority_when_multiple_conditions_hit():
    fields = _full_fields()

    # Attachment missing beats a damaged file: if the pair never arrived,
    # there is nothing whose OCR quality or emptiness can be judged.
    missing_email = EmailMessage(
        email_id="p1",
        subject="please compare the draft BL",
        body_text="Please compare the draft BL. The attachment is missing and was not received.",
        attachment_paths=["si.pdf"],
    )
    empty_si = ExtractedDocument(filename="si.pdf", kind="si", text="", parser_used="vision")
    r1 = health_check(missing_email, [empty_si])
    assert r1.reason == ReviewReason.MISSING_ATTACHMENT

    # Unreadable beats wrong type: a scan with no text layer cannot be
    # classified as an invoice even if a fragment happens to say so.
    si = ExtractedDocument(
        filename="si.txt",
        kind="si",
        text="SHIPPING INSTRUCTION\n" + "x" * 80,
        fields=fields,
    )
    faint_invoice = ExtractedDocument(
        filename="bl.pdf",
        kind="other",
        text="commercial invoice",
        parser_used="vision",
        fields={},
    )
    r2 = health_check(
        EmailMessage(email_id="p2", subject="SI vs BL", attachment_paths=["si.txt", "bl.pdf"]),
        [si, faint_invoice],
        si=si,
        bl=faint_invoice,
    )
    assert r2.reason == ReviewReason.UNREADABLE

    # Wrong type beats a missing field: if the file is not an SI/BL,
    # asking which compare field is blank is meaningless.
    si_tba = ExtractedDocument(
        filename="si.txt",
        kind="si",
        text="SHIPPING INSTRUCTION\n" + "x" * 80,
        fields={**fields, "shipper": _fv("shipper", "TBA")},
    )
    invoice = ExtractedDocument(
        filename="inv.pdf",
        kind="other",
        text="COMMERCIAL INVOICE\n" + "x" * 80,
        fields=fields,
    )
    r3 = health_check(
        EmailMessage(email_id="p3", subject="SI vs BL", attachment_paths=["si.txt", "inv.pdf"]),
        [si_tba, invoice],
        si=si_tba,
        bl=invoice,
    )
    assert r3.reason == ReviewReason.WRONG_DOC_TYPE
