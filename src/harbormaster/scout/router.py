from .llm_classifier import classify_by_llm
from .rules import classify_by_rule


def route_email(content: str) -> tuple[str, float, str]:
    label = classify_by_rule(content)
    if label:
        return label, 1.0, "rule"
    llm_label, confidence = classify_by_llm(content)
    return llm_label, confidence, "llm"
