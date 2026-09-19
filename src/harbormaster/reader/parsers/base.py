"""Parser protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseParser(ABC):
    name: str = "base"

    @abstractmethod
    def parse(self, path: Path) -> str:
        """Return extracted plain text."""
