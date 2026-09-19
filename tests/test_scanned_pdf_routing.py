"""Scanned (image-only) PDFs must go through VisionParser, not PdfParser."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from harbormaster.reader.detector import pdf_has_text, select_parser
from harbormaster.reader.extractor import FieldExtractor
from harbormaster.reader.parsers.vision_parser import VisionParser


def _image_only_pdf(stem: Path) -> Path:
    png = stem.with_suffix(".png")
    img = Image.new("RGB", (900, 240), "white")
    ImageDraw.Draw(img).text((24, 80), "SHIPPING INSTRUCTION Shipper: ACME CORP", fill=(0, 0, 0))
    img.save(png)
    import pymupdf

    doc = pymupdf.open()
    try:
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, filename=str(png))
        pdf = stem.with_suffix(".pdf")
        doc.save(pdf)
    finally:
        doc.close()
    return pdf


def test_text_pdf_still_uses_pdf_parser(tmp_path: Path):
    pdf = tmp_path / "typed.pdf"
    import pymupdf

    doc = pymupdf.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "SHIPPING INSTRUCTION\nShipper: ACME CORP\n" + ("x" * 80))
        doc.save(pdf)
    finally:
        doc.close()
    assert pdf_has_text(pdf) is True
    assert select_parser(pdf).name == "pdf"


def test_scanned_pdf_routes_to_vision(tmp_path: Path):
    pdf = _image_only_pdf(tmp_path / "scan")
    assert pdf_has_text(pdf) is False
    assert pdf_has_text(pdf, min_chars=1) is False
    parser = select_parser(pdf)
    assert isinstance(parser, VisionParser)
    assert parser.name == "vision"
    doc = FieldExtractor(rules_only=True, degrade=True).extract_path(pdf)
    assert doc.parser_used == "vision"
