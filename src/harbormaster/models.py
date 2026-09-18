from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VerdictState(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNCERTAIN = "UNCERTAIN"


@dataclass(slots=True)
class Evidence:
    raw_text: str
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    source: str = "text"


@dataclass(slots=True)
class FieldValue:
    field: str
    value: str
    confidence: float = 1.0
    evidence: Evidence | None = None


@dataclass(slots=True)
class CourtDecision:
    verdict: VerdictState
    reason: str
    transcript: list[str] = field(default_factory=list)
