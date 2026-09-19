"""Attachment sniff + read helpers."""

from __future__ import annotations

import mimetypes
from pathlib import Path


def sniff(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if mime:
        return mime
    suffix = path.suffix.lower()
    return {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "application/octet-stream")


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()
