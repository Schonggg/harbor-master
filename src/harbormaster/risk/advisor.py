"""Human-readable action copy for Bridge cards."""

from __future__ import annotations

from harbormaster.models import CaseCard, CaseVerdict


def advise_case(card: CaseCard) -> str:
    if card.verdict == CaseVerdict.CLEAR:
        return "CLEAR — no material discrepancy; safe to proceed."
    if card.verdict == CaseVerdict.HOLD:
        fields = ", ".join(card.mismatch_fields) or "unknown"
        return f"HOLD — mismatch on {fields}. Request amendment before release."
    fields = ", ".join(card.uncertain_fields) or "review queue"
    return f"PILOT — human review required ({fields})."
