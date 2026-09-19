"""Scanned docs: Vision LLM primary, pytesseract OCR fallback."""

from __future__ import annotations

import base64
from pathlib import Path

from harbormaster.config import get_settings
from harbormaster.llm.client import get_llm_client, llm_available
from harbormaster.reader.parsers.base import BaseParser


class VisionParser(BaseParser):
    name = "vision"

    def parse(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = self._vision_pdf(path)
            if text.strip():
                return text
            return self._tesseract_pdf(path)
        if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
            text = self._vision_image(path)
            if text.strip():
                return text
            return self._tesseract_image(path)
        return ""

    def _vision_pdf(self, path: Path) -> str:
        try:
            import fitz
        except Exception:
            return ""
        doc = fitz.open(path)
        chunks: list[str] = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            png = pix.tobytes("png")
            text = self._vision_bytes(png, "image/png")
            if text.strip():
                chunks.append(text)
        return "\n".join(chunks)

    def _vision_image(self, path: Path) -> str:
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
        }.get(path.suffix.lower(), "image/png")
        return self._vision_bytes(path.read_bytes(), mime)

    def _vision_bytes(self, data: bytes, mime: str) -> str:
        if not llm_available():
            return ""
        try:
            client = get_llm_client()
            settings = get_settings()
            b64 = base64.b64encode(data).decode("ascii")
            return client.chat(
                [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract all shipping document text verbatim. No commentary.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                        ],
                    }
                ],
                model=settings.vision_model,
                max_tokens=2500,
            )
        except Exception:
            return ""

    def _tesseract_pdf(self, path: Path) -> str:
        try:
            import fitz
            import pytesseract
            from PIL import Image
        except Exception:
            return ""
        doc = fitz.open(path)
        chunks: list[str] = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            chunks.append(pytesseract.image_to_string(img) or "")
        return "\n".join(chunks)

    def _tesseract_image(self, path: Path) -> str:
        try:
            import pytesseract
            from PIL import Image
        except Exception:
            return ""
        return pytesseract.image_to_string(Image.open(path)) or ""
