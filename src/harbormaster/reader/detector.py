"""Detect PDF text layer → choose parser."""

from __future__ import annotations

from pathlib import Path

from harbormaster.ingest.attachment import sniff
from harbormaster.reader.parsers import DocxParser, PdfParser, TextParser, VisionParser, XlsxParser
from harbormaster.reader.parsers.base import BaseParser


def pdf_has_text(path: Path, min_chars: int = 40) -> bool:
    try:
        import pymupdf

        doc = pymupdf.open(path)
        try:
            text = "".join((page.get_text() or "") for page in list(doc)[:2])
        finally:
            doc.close()
        return len(text.strip()) >= min_chars
    except Exception:
        return False


def select_parser(path: Path) -> BaseParser:
    mime = sniff(path)
    suffix = path.suffix.lower()
    if suffix == ".txt" or mime.startswith("text/"):
        return TextParser()
    if suffix == ".docx":
        return DocxParser()
    if suffix in {".xlsx", ".xls"} or "spreadsheet" in mime:
        return XlsxParser()
    if suffix == ".pdf" or mime == "application/pdf":
        if pdf_has_text(path):
            return PdfParser()
        return PdfParser()
    return TextParser()
