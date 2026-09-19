"""Few-shot LLM classifier for the five official categories."""

from __future__ import annotations

from harbormaster.config import load_prompt
from harbormaster.llm.client import get_llm_client, llm_available
from harbormaster.models import (
    CATEGORY_TO_SCOUT,
    Category,
    EmailMessage,
    ScoutLabel,
    ScoutResult,
)


class LLMClassifier:
    def __init__(self, model: str | None = None) -> None:
        self.model = model
        self.prompt = load_prompt("classify.md")

    def classify(self, email: EmailMessage) -> ScoutResult:
        if not llm_available():
            return ScoutResult(
                category=Category.GENERAL,
                label=ScoutLabel.UNKNOWN,
                confidence=0.0,
                reason="no LLM API key",
                route="llm",
                degraded=True,
            )
        names = ", ".join(a.filename or a.path for a in email.attachments) or ", ".join(
            email.attachment_paths
        )
        user = (
            f"Subject: {email.subject}\nAttachments: {names}\n\nBody:\n{email.body_text[:4000]}"
        )
        try:
            client = get_llm_client()
            data = client.cached_json(
                "classify",
                f"{email.email_id}\n{user}",
                [
                    {"role": "system", "content": self.prompt},
                    {"role": "user", "content": user},
                ],
                model=self.model,
            )
            category = _parse_category(data)
            label = _parse_label(data, category)
            return ScoutResult(
                category=category,
                label=label,
                confidence=float(data.get("confidence", 0.5)),
                reason=str(data.get("reason", "")),
                route="llm",
            )
        except Exception as exc:  # noqa: BLE001 — degrade path
            return ScoutResult(
                category=Category.GENERAL,
                label=ScoutLabel.UNKNOWN,
                confidence=0.0,
                reason=f"llm error: {exc}",
                route="llm",
                degraded=True,
            )


def _parse_category(data: dict) -> Category:
    raw = str(data.get("category") or data.get("label") or "GENERAL").strip()
    key = raw.upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "BILL_OF_LADING": Category.BL_COMPARISON,
        "BL": Category.BL_COMPARISON,
        "SHIPPING_INSTRUCTION": Category.SI_REQUEST,
        "SI": Category.SI_REQUEST,
        "INVOICE": Category.INVOICE_QUERY,
        "INVOICE_OR_CHARGES": Category.INVOICE_QUERY,
        "OPERATIONAL_NOISE": Category.SPAM,
        "UNKNOWN": Category.GENERAL,
    }
    if key in Category.__members__:
        return Category[key]
    try:
        return Category(key)
    except ValueError:
        return aliases.get(key, Category.GENERAL)


def _parse_label(data: dict, category: Category) -> ScoutLabel:
    raw = str(data.get("scout_label") or "").strip()
    if raw:
        try:
            return ScoutLabel(raw)
        except ValueError:
            pass
    return CATEGORY_TO_SCOUT[category]
