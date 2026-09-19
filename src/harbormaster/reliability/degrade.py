"""Degrade to rules-only when LLM is down."""

from __future__ import annotations

from harbormaster.models import FailureCode


def should_degrade(llm_ok: bool, chaos_flags: list[str]) -> tuple[bool, list[FailureCode]]:
    codes: list[FailureCode] = []
    if "llm_timeout" in chaos_flags:
        codes.append(FailureCode.LLM_TIMEOUT)
        codes.append(FailureCode.CHAOS_INJECTED)
        return True, codes
    if not llm_ok:
        codes.append(FailureCode.DEGRADED_RULES_ONLY)
        return True, codes
    return False, codes
