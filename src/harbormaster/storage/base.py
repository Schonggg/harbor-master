from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ObjectRef:
    key: str
    backend: str
    bytes: int
    content_type: str
    uri: str


class ObjectStore(Protocol):
    backend: str

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> ObjectRef: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def health(self) -> dict: ...
