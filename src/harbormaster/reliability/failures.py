"""Map failures → PILOT reason codes."""

from __future__ import annotations

from harbormaster.models import FailureCode

PILOT_REASONS: dict[FailureCode, str] = {
    FailureCode.LLM_TIMEOUT: "Upstream model timed out — rules-only path",
    FailureCode.LLM_INVALID_JSON: "Model returned unparseable JSON",
    FailureCode.ATTACHMENT_CORRUPT: "Attachment unreadable",
    FailureCode.OCR_GARBLED: "OCR confidence collapsed",
    FailureCode.EMPTY_EMAIL: "Empty message — nothing to adjudicate",
    FailureCode.PARSER_MISS: "No parser matched attachment",
    FailureCode.DEGRADED_RULES_ONLY: "Running in degraded mode",
    FailureCode.CHAOS_INJECTED: "Demo chaos injection active",
}


def reason_for(code: FailureCode) -> str:
    return PILOT_REASONS.get(code, code.value)
