"""False-alarm report — strategies that prevented HOLD."""

from __future__ import annotations

from collections import Counter


def avoided_false_alarms(field_verdicts: list[dict]) -> dict:
    """Count MATCH outcomes that had a winning_strategy (charge was raised then defended)."""
    by_strategy: Counter[str] = Counter()
    for fv in field_verdicts:
        if fv.get("state") == "MATCH" and fv.get("winning_strategy"):
            by_strategy[fv["winning_strategy"]] += 1
    return {"avoided": int(sum(by_strategy.values())), "by_strategy": dict(by_strategy)}
