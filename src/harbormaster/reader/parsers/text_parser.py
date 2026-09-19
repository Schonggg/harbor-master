from __future__ import annotations

from pathlib import Path

from harbormaster.reader.parsers.base import BaseParser


class TextParser(BaseParser):
    name = "text"

    def parse(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")
