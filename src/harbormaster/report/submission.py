"""Build official submission.json and the Bridge-shaped payload."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harbormaster.court.aggregate import aggregate
from harbormaster.models import (
    Category,
    CaseCard,
    CaseVerdict,
    EmailMessage,
    EmailVerdict,
    ReviewReason,
    Submission,
)
from harbormaster.official import assemble, decided_by_of


def build_bridge_submission(email: EmailMessage, card: CaseCard) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "email_id": email.email_id,
        "subject": email.subject,
        "case_id": card.case_id,
        "verdict": card.verdict.value,
        "degraded": card.degraded,
        "failure_codes": [c.value for c in card.failure_codes],
        "fields": [
            {
                "name": fv.field,
                "state": fv.state.value,
                "winning_strategy": fv.winning_strategy,
                "rationale": fv.rationale,
                "risk_level": fv.risk_level.value,
                "exposure_usd": fv.exposure_usd,
                "left": fv.charge.left.raw_value if fv.charge else None,
                "right": fv.charge.right.raw_value if fv.charge else None,
            }
            for fv in card.field_verdicts
        ],
        "total_exposure_usd": card.total_exposure_usd,
        "scout": card.scout.model_dump(mode="json") if card.scout else None,
    }


def build_submission(email: EmailMessage, card: CaseCard) -> dict[str, Any]:
    """Per-email official record (also kept on the run payload)."""
    official = card.official or build_official_verdict(card)
    return official.as_submission_dict()


def build_official_verdict(card: CaseCard) -> EmailVerdict:
    if card.official:
        return card.official
    decided = decided_by_of(card.scout)
    category = card.scout.category if card.scout else Category.GENERAL
    if category != Category.BL_COMPARISON:
        return assemble(category=category, decided_by=decided)
    if card.verdict == CaseVerdict.PILOT and not card.field_verdicts:
        return assemble(
            category=Category.BL_COMPARISON,
            gate_reason=ReviewReason.UNREADABLE,
            decided_by=decided,
        )
    _, defect_fields = aggregate(card.field_verdicts)
    return assemble(
        category=Category.BL_COMPARISON,
        defect_fields=defect_fields,
        decided_by=decided,
    )


def assemble_submission(results: dict[str, EmailVerdict]) -> Submission:
    return Submission(results)


def validate_submission(payload: dict[str, Any], required_ids: list[str]) -> Submission:
    submission = Submission.model_validate(
        {str(eid): EmailVerdict.model_validate(rec) for eid, rec in payload.items()}
    )
    submission.validate_coverage([str(i) for i in required_ids])
    return submission


def write_submission(
    results: dict[str, EmailVerdict],
    required_ids: list[str],
    path: Path,
) -> Path:
    submission = assemble_submission(results)
    submission.validate_coverage(required_ids)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        __import__("json").dumps(submission.as_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path
