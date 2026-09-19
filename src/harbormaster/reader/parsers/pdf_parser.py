from __future__ import annotations

from pathlib import Path

from harbormaster.reader.parsers.base import BaseParser


class PdfParser(BaseParser):
    name = "pdf"

    def parse(self, path: Path) -> str:
        pages = self.parse_pages(path)
        return "\n".join(p["text"] for p in pages)

    def parse_pages(self, path: Path) -> list[dict]:
        fitz_pages = _pymupdf_pages(path)
        if fitz_pages and any(p["text"].strip() for p in fitz_pages):
            return fitz_pages
        plumber_pages = _pdfplumber_pages(path)
        if plumber_pages and any(p["text"].strip() for p in plumber_pages):
            return plumber_pages
        return fitz_pages or plumber_pages


def _pdfplumber_pages(path: Path) -> list[dict]:
    try:
        import pdfplumber

        out: list[dict] = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                words = []
                try:
                    words = page.extract_words() or []
                except Exception:
                    words = []
                text = page.extract_text() or ""
                bboxes = [
                    {
                        "page": i,
                        "x0": float(w.get("x0", 0)),
                        "y0": float(w.get("top", 0)),
                        "x1": float(w.get("x1", 0)),
                        "y1": float(w.get("bottom", 0)),
                        "text": w.get("text") or "",
                    }
                    for w in words
                ]
                out.append({"page": i, "text": text, "bboxes": bboxes})
        return out
    except Exception:
        return []


def _pymupdf_pages(path: Path) -> list[dict]:
    try:
        import pymupdf

        doc = pymupdf.open(path)
    except Exception:
        return []
    try:
        out: list[dict] = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text() or ""
            bboxes = []
            for block in page.get_text("blocks"):
                if len(block) < 5 or not isinstance(block[4], str):
                    continue
                x0, y0, x1, y1, raw = block[0], block[1], block[2], block[3], block[4]
                bboxes.append(
                    {
                        "page": i,
                        "x0": float(x0),
                        "y0": float(y0),
                        "x1": float(x1),
                        "y1": float(y1),
                        "text": raw.strip(),
                    }
                )
            out.append({"page": i, "text": text, "bboxes": bboxes})
        return out
    finally:
        doc.close()
