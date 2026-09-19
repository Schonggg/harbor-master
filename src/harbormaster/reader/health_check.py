"""Detect the four NEEDS_REVIEW conditions BEFORE field comparison runs.

review_reason is a fixed four-value enum used only with status=NEEDS_REVIEW:
  missing_attachment | unreadable | wrong_doc_type | missing_value
"""

from __future__ import annotations

import re
from pathlib import Path

from harbormaster.config import runtime_thresholds
from harbormaster.models import (
    COMPARE_FIELDS,
    EmailMessage,
    ExtractedDocument,
    HealthCheckResult,
    ReviewReason,
)
from harbormaster.official.gate import (
    claims_attachment_missing,
    is_placeholder,
    scene_a_skip_missing_attachment,
)

_SI_MARKERS = re.compile(
    r"\b(shipping instruction|\bSI\b|shipper|consignee|port of loading)\b",
    re.I,
)
_BL_MARKERS = re.compile(
    r"\b(bill of lading|\bB/?L\b|ocean bill|draft bl|negotiable)\b",
    re.I,
)
_WRONG_TYPE = re.compile(
    r"\b(commercial invoice|packing list|certificate of origin|imdg|"
    r"dangerous goods|msds|booking confirmation only)\b",
    re.I,
)
_NUM_TOKEN = re.compile(r"\d+(?:[.,]\d+)?")
_CURRENCY = re.compile(r"(?:USD|EUR|GBP|CNY|RMB|SGD|JPY|HKD|[$¥€£])", re.I)
_CARTON_LINE = re.compile(r"(?:CTN-|CARTON\s*NO\.?)\s*\d+", re.I)
_COO_ORIGIN = re.compile(r"country of origin", re.I)
_COO_ISSUER = re.compile(
    r"chamber of commerce|issued by|issuing (?:body|authority)|this is to certify",
    re.I,
)
_BL_CORE = ("port_of_loading", "port_of_discharge", "container_count")
_SI_CORE = ("shipper", "consignee", "port_of_loading")


def _text_of(doc: ExtractedDocument | None) -> str:
    if not doc:
        return ""
    if doc.text.strip():
        return doc.text
    return " ".join(fv.raw_value for fv in doc.fields.values())


def _looks_like(doc: ExtractedDocument | None, kind: str) -> bool:
    if not doc:
        return False
    if doc.kind == kind:
        return True
    blob = f"{doc.filename}\n{_text_of(doc)}"
    if kind == "si":
        return bool(_SI_MARKERS.search(blob))
    if kind == "bl":
        return bool(_BL_MARKERS.search(blob))
    return False


def classify_doc_kind(doc: ExtractedDocument) -> str:
    name = doc.filename.lower().replace("\\", "/")
    stem = Path(name).name
    text = _text_of(doc)
    blob = f"{name}\n{text[:1500]}"
    if re.search(r"(^|[_\-\s/])si(\.|_|-|$)", stem) or "shipping_instruction" in stem:
        return "si"
    if re.search(r"(^|[_\-\s/])bl(\.|_|-|$)", stem) or "bill_of_lading" in stem or "draft_bl" in stem:
        return "bl"
    si_hit = bool(_SI_MARKERS.search(blob))
    bl_hit = bool(_BL_MARKERS.search(blob))
    if si_hit and not bl_hit:
        return "si"
    if bl_hit and not si_hit:
        return "bl"
    if si_hit and bl_hit:
        # Prefer filename; else BL if "bill of lading" appears first.
        si_pos = blob.lower().find("shipping")
        bl_pos = blob.lower().find("bill of lading")
        if bl_pos >= 0 and (si_pos < 0 or bl_pos < si_pos):
            return "bl"
        return "si"
    if _WRONG_TYPE.search(blob):
        return "other"
    if looks_structurally_wrong(doc, "bl") or looks_structurally_wrong(doc, "si"):
        return "other"
    return "unknown"


def _field_missing(doc: ExtractedDocument, name: str) -> bool:
    fv = doc.fields.get(name)
    if fv is None:
        return True
    return is_placeholder(fv.raw_value or "")


def _core_fields_missing(doc: ExtractedDocument, names: tuple[str, ...]) -> bool:
    return all(_field_missing(doc, name) for name in names)


def _invoice_table_lines(text: str) -> int:
    """Rows that look like qty x amount: two numbers plus a currency token."""
    n = 0
    for line in (text or "").splitlines():
        if len(_NUM_TOKEN.findall(line)) >= 2 and _CURRENCY.search(line):
            n += 1
    return n


def _packing_list_signal(text: str) -> bool:
    return sum(1 for line in (text or "").splitlines() if _CARTON_LINE.search(line)) >= 3


def _certificate_of_origin_signal(text: str) -> bool:
    blob = text or ""
    return bool(_COO_ORIGIN.search(blob) and _COO_ISSUER.search(blob))


def looks_structurally_wrong(doc: ExtractedDocument, expected_kind: str) -> bool:
    """Keyword-free check: does this document fail the shape of expected_kind?

    Both a missing-core-fields signal and a foreign-document layout signal
    must fire. Field gaps alone (failed OCR on a real BL) are not enough.
    """
    text = _text_of(doc)
    if expected_kind == "bl":
        return _core_fields_missing(doc, _BL_CORE) and _invoice_table_lines(text) > 2
    if expected_kind == "si":
        foreign = _packing_list_signal(text) or _certificate_of_origin_signal(text)
        return _core_fields_missing(doc, _SI_CORE) and foreign
    return False


def pair_si_bl(
    docs: list[ExtractedDocument],
) -> tuple[ExtractedDocument | None, ExtractedDocument | None]:
    si = next((d for d in docs if d.kind == "si"), None)
    bl = next((d for d in docs if d.kind == "bl"), None)
    if si and bl:
        return si, bl
    leftover = [d for d in docs if d is not si and d is not bl]
    if not si and leftover:
        si = leftover.pop(0)
        si.kind = si.kind if si.kind != "unknown" else "si"
    if not bl and leftover:
        bl = leftover.pop(0)
        bl.kind = bl.kind if bl.kind != "unknown" else "bl"
    return si, bl


def check_readability(doc: ExtractedDocument | None) -> bool:
    if not doc:
        return False
    if doc.parser_used == "corrupt":
        return False
    min_chars = int(runtime_thresholds().unreadable_min_chars)
    text = _text_of(doc)
    if len(text.strip()) >= min_chars:
        return True
    if doc.fields:
        return True
    return False


def missing_compare_fields(
    si: ExtractedDocument | None,
    bl: ExtractedDocument | None,
) -> list[str]:
    missing: list[str] = []
    for name in COMPARE_FIELDS:
        left = si.fields.get(name) if si else None
        right = bl.fields.get(name) if bl else None
        # gross_weight legacy alias
        if name == "gross_weight_kg":
            left = left or (si.fields.get("gross_weight") if si else None)
            right = right or (bl.fields.get("gross_weight") if bl else None)
        left_ok = bool(left and not is_placeholder(left.raw_value or left.value))
        right_ok = bool(right and not is_placeholder(right.raw_value or right.value))
        if not left_ok or not right_ok:
            missing.append(name)
    return missing


def health_check(
    email: EmailMessage,
    docs: list[ExtractedDocument],
    *,
    si: ExtractedDocument | None = None,
    bl: ExtractedDocument | None = None,
) -> HealthCheckResult:
    """Return ok=False with a single review_reason, in spec priority order."""
    if si is None or bl is None:
        si, bl = pair_si_bl(docs)

    has_named_files = bool(email.attachments or email.attachment_paths)
    body_has_pair = "=== SHIPPING INSTRUCTION" in email.body_text and "=== BILL OF LADING" in email.body_text
    if not docs and not body_has_pair:
        if scene_a_skip_missing_attachment(email):
            return HealthCheckResult(
                ok=True,
                detail="scene A: request to send files is not missing_attachment",
            )
        return HealthCheckResult(
            ok=False,
            reason=ReviewReason.MISSING_ATTACHMENT,
            detail="no SI/BL attachments and no inline document blocks",
        )
    if si is None or bl is None:
        if scene_a_skip_missing_attachment(email) and not claims_attachment_missing(email):
            return HealthCheckResult(
                ok=True,
                detail="scene A: request to send files is not missing_attachment",
            )
        return HealthCheckResult(
            ok=False,
            reason=ReviewReason.MISSING_ATTACHMENT,
            detail="could not pair an SI with a BL",
            si_filename=si.filename if si else None,
            bl_filename=bl.filename if bl else None,
        )

    if not check_readability(si) or not check_readability(bl):
        return HealthCheckResult(
            ok=False,
            reason=ReviewReason.UNREADABLE,
            detail="SI or BL text layer empty / OCR failed",
            si_filename=si.filename,
            bl_filename=bl.filename,
        )

    si_ok = _looks_like(si, "si") or si.kind in {"si", "unknown"}
    bl_ok = _looks_like(bl, "bl") or bl.kind in {"bl", "unknown"}
    if si.kind == "other" or bl.kind == "other" or (has_named_files and not (si_ok and bl_ok)):
        if si.kind == "other" or bl.kind == "other":
            return HealthCheckResult(
                ok=False,
                reason=ReviewReason.WRONG_DOC_TYPE,
                detail="attachment is not an SI or BL",
                si_filename=si.filename,
                bl_filename=bl.filename,
            )

    missing = missing_compare_fields(si, bl)
    if missing:
        return HealthCheckResult(
            ok=False,
            reason=ReviewReason.MISSING_VALUE,
            detail="missing: " + ", ".join(missing),
            si_filename=si.filename,
            bl_filename=bl.filename,
            missing_fields=missing,
        )

    return HealthCheckResult(
        ok=True,
        si_filename=si.filename,
        bl_filename=bl.filename,
    )


def split_inline_si_bl(body: str) -> tuple[str, str] | None:
    if "=== SHIPPING INSTRUCTION" not in body or "=== BILL OF LADING" not in body:
        return None
    si = body.split("=== SHIPPING INSTRUCTION", 1)[1]
    si = si.split("=== BILL OF LADING", 1)[0]
    bl = body.split("=== BILL OF LADING", 1)[1]
    return si, bl


def local_path(path_str: str) -> Path:
    return Path(path_str)
