from __future__ import annotations

from pathlib import Path

from harbormaster.reader.parsers.base import BaseParser


class DocxParser(BaseParser):
    name = "docx"

    def parse(self, path: Path) -> str:
        from docx import Document

        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text)
