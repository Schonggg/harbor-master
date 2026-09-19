"""Pipeline state dataclass (LangGraph-compatible shape without hard dep)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harbormaster.models import (
    CaseCard,
    CourtTranscript,
    EmailMessage,
    EmailVerdict,
    ExtractedDocument,
    FailureCode,
    HealthCheckResult,
    ScoutResult,
)


@dataclass
class PipelineState:
    email: EmailMessage | None = None
    scout: ScoutResult | None = None
    left_doc: ExtractedDocument | None = None
    right_doc: ExtractedDocument | None = None
    docs: list[ExtractedDocument] = field(default_factory=list)
    health: HealthCheckResult | None = None
    card: CaseCard | None = None
    transcript: CourtTranscript | None = None
    submission: dict[str, Any] | None = None
    official: EmailVerdict | None = None
    degrade: bool = False
    rules_only: bool = False
    two_value: bool = False
    save_board: bool = True
    chaos: list[str] = field(default_factory=list)
    failures: list[FailureCode] = field(default_factory=list)
    interrupt: str | None = None
