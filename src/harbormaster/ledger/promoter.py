"""Promote pilot decisions into permanent ledger rules."""

from __future__ import annotations

from harbormaster.ledger.store import LedgerStore, normalized_pair_key
from harbormaster.models import LedgerRule, PilotDecision, PilotReview


class Promoter:
    def __init__(self, store: LedgerStore | None = None) -> None:
        self.store = store or LedgerStore()

    def promote(
        self,
        review: PilotReview,
        left_value: str,
        right_value: str,
    ) -> LedgerRule | None:
        self.store.add_review(review)
        if not review.promote_to_ledger:
            return None
        if review.decision == PilotDecision.DEFER:
            return None
        rule = LedgerRule(
            field=review.field,
            left_pattern=left_value,
            right_pattern=right_value,
            normalized_key=normalized_pair_key(left_value, right_value),
            decision=review.decision,
            source_case_id=review.case_id,
            created_by=review.reviewer,
            note=review.note,
        )
        self.store.add_rule(rule)
        return rule
