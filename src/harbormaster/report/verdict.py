"""CLEAR / HOLD / PILOT card builder."""

from __future__ import annotations

from harbormaster.models import (
    CaseCard,
    CaseVerdict,
    EmailMessage,
    FailureCode,
    FieldVerdict,
    ScoutResult,
)
from harbormaster.risk.advisor import advise_case


def build_card(
    *,
    email: EmailMessage,
    scout: ScoutResult | None,
    field_verdicts: list[FieldVerdict],
    verdict: CaseVerdict,
    exposure: float,
    failures: list[FailureCode],
    degraded: bool,
) -> CaseCard:
    card = CaseCard(
        email_id=email.email_id,
        subject=email.subject,
        verdict=verdict,
        scout=scout,
        field_verdicts=field_verdicts,
        total_exposure_usd=exposure,
        failure_codes=failures,
        degraded=degraded,
    )
    # attach advisory text into first advise if empty
    _ = advise_case(card)
    return card
