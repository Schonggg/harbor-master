"""Chaos injectors for live demo smash buttons + official fault types."""

from __future__ import annotations

from harbormaster.models import EmailMessage, ExtractedDocument, FailureCode, FieldValue

CHAOS_TYPES = (
    "llm_timeout",
    "ocr_garble",
    "attachment_corrupt",
    "empty_email",
    "strip_attachment",
    "blur_scan",
    "kill_llm",
    "corrupt_field",
)

_ALIASES = {
    "strip_attachment": "attachment_corrupt",
    "blur_scan": "ocr_garble",
    "kill_llm": "llm_timeout",
}


def normalize_flags(flags: list[str]) -> list[str]:
    return [_ALIASES.get(f, f) for f in flags]


def apply_chaos(email: EmailMessage, flags: list[str]) -> tuple[EmailMessage, list[FailureCode]]:
    codes: list[FailureCode] = []
    e = email.model_copy(deep=True)
    for flag in normalize_flags(flags):
        if flag == "llm_timeout":
            codes.append(FailureCode.LLM_TIMEOUT)
            codes.append(FailureCode.CHAOS_INJECTED)
        elif flag == "ocr_garble":
            e.body_text = _garble(e.body_text)
            codes.append(FailureCode.OCR_GARBLED)
            codes.append(FailureCode.CHAOS_INJECTED)
        elif flag == "attachment_corrupt":
            e.attachment_paths = ["__corrupt__/missing.bin"]
            e.attachments = []
            codes.append(FailureCode.ATTACHMENT_CORRUPT)
            codes.append(FailureCode.CHAOS_INJECTED)
        elif flag == "empty_email":
            e.subject = ""
            e.body_text = ""
            e.attachment_paths = []
            e.attachments = []
            codes.append(FailureCode.EMPTY_EMAIL)
            codes.append(FailureCode.CHAOS_INJECTED)
        elif flag == "corrupt_field":
            codes.append(FailureCode.CHAOS_INJECTED)
    return e, codes


def corrupt_extracted(doc: ExtractedDocument | None) -> ExtractedDocument | None:
    if not doc or not doc.fields:
        return doc
    name = next(iter(doc.fields))
    fv = doc.fields[name]
    doc.fields[name] = FieldValue(
        name=fv.name,
        raw_value=fv.raw_value + " [CORRUPT]",
        confidence=fv.confidence,
        evidence=fv.evidence,
    )
    return doc


def _garble(text: str) -> str:
    table = str.maketrans({"O": "0", "I": "1", "S": "5", "B": "8", "A": "4"})
    return text.translate(table)
