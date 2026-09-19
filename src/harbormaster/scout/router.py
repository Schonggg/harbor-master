"""Rules → LLM. Always commits to one of the five official categories."""

from __future__ import annotations

from harbormaster.config import runtime_thresholds
from harbormaster.models import Category, EmailMessage, ScoutLabel, ScoutResult
from harbormaster.scout.llm_classifier import LLMClassifier
from harbormaster.scout.rules import commit_category, rule_classify


class ScoutRouter:
    def __init__(self, llm: LLMClassifier | None = None, degrade: bool = False) -> None:
        self.llm = llm or LLMClassifier()
        self.degrade = degrade

    def route(self, email: EmailMessage) -> ScoutResult:
        thr = runtime_thresholds()
        ruled = rule_classify(email)
        if ruled and ruled.confidence >= thr.scout_rule_confidence:
            return commit_category(ruled)

        if self.degrade:
            fallback = ruled or ScoutResult(
                category=Category.GENERAL,
                label=ScoutLabel.UNKNOWN,
                confidence=0.4,
                reason="degraded: rules only",
                route="unknown",
                degraded=True,
            )
            return commit_category(fallback)

        llm_result = self.llm.classify(email)
        if llm_result.confidence >= thr.scout_llm_min_confidence and not llm_result.degraded:
            return commit_category(llm_result)
        if ruled and ruled.confidence >= thr.scout_llm_min_confidence:
            return commit_category(
                ruled.model_copy(update={"reason": f"{ruled.reason} (llm unavailable or low conf)"})
            )
        if llm_result.degraded or llm_result.confidence == 0.0:
            return commit_category(
                ScoutResult(
                    category=Category.GENERAL,
                    label=ScoutLabel.OPERATIONAL_NOISE,
                    confidence=0.51,
                    reason=llm_result.reason or "llm unavailable → GENERAL",
                    route="llm",
                    degraded=True,
                )
            )
        return commit_category(llm_result)
