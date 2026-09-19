"""Confusion helpers for scout labels / field states."""

from __future__ import annotations

from collections import Counter, defaultdict


def confusion(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """pairs of (gold, pred) → nested counts."""
    matrix: dict[str, dict[str, int]] = defaultdict(Counter)
    for gold, pred in pairs:
        matrix[gold][pred] += 1
    return {g: dict(c) for g, c in matrix.items()}


def field_pr(pairs: list[tuple[str, str]], positive: str = "MISMATCH") -> dict[str, float]:
    tp = fp = fn = 0
    for gold, pred in pairs:
        if pred == positive and gold == positive:
            tp += 1
        elif pred == positive and gold != positive:
            fp += 1
        elif pred != positive and gold == positive:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {"precision": precision, "recall": recall, "tp": tp, "fp": fp, "fn": fn}
