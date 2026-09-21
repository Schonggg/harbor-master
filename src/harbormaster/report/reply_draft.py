"""Outbox: turn a verdict into a sendable reply. Never auto-sent.

This is product copy, not scoring. Defect fields still come only from L5/assemble.
English-only — no bilingual labels or Chinese placeholders.
"""

from __future__ import annotations

from typing import Any

from harbormaster.config import load_prompt
from harbormaster.models import CaseCard, ReviewReason

FIELD_LABEL = {
    "shipper": "Shipper",
    "consignee": "Consignee",
    "notify_party": "Notify Party",
    "port_of_loading": "POL",
    "port_of_discharge": "POD",
    "container_count": "Containers",
    "gross_weight_kg": "Gross weight",
}

SIGN = "\n\n[Operator name] / Harbormaster Desk"


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _si_bl(fv: Any) -> tuple[str, str]:
    if fv is None:
        return "—", "—"
    if isinstance(fv, dict):
        charge = fv.get("charge") or {}
        left = (charge.get("left") or {}).get("raw_value") or "—"
        right = (charge.get("right") or {}).get("raw_value") or "—"
        return str(left), str(right)
    charge = getattr(fv, "charge", None)
    if not charge:
        return "—", "—"
    return charge.left.raw_value or "—", charge.right.raw_value or "—"


def generate_outbox_message(
    *,
    subject: str = "",
    body: str = "",
    category: str | None = None,
    status: str | None = None,
    review_reason: str | None = None,
    defect_fields: list[str] | None = None,
    field_verdicts: list[Any] | None = None,
    bridge_verdict: str | None = None,
) -> str | None:
    """Professional English reply for the operator to send. None if the mail is only archived."""
    del body  # kept for call-site compatibility; English copy does not branch on source language
    cat = (category or "").upper()
    st = (status or "").upper()
    verdict = (bridge_verdict or "").upper()
    defects = list(defect_fields or [])
    by_field = {}
    for fv in field_verdicts or []:
        name = fv.get("field") if isinstance(fv, dict) else getattr(fv, "field", None)
        if name:
            by_field[name] = fv

    if cat and cat != "BL_COMPARISON" and verdict not in {"CLEAR", "HOLD", "PILOT"}:
        return None

    if verdict == "HOLD" or st == "MISMATCH" or defects:
        lines = []
        names = defects or [
            (fv.get("field") if isinstance(fv, dict) else getattr(fv, "field", ""))
            for fv in (field_verdicts or [])
            if (fv.get("state") if isinstance(fv, dict) else getattr(fv, "state", None)) == "MISMATCH"
        ]
        names = [n for n in names if n]
        lines.append(
            f"Regarding '{subject or 'this booking'}': the draft BL does not match the SI on the fields below. Please confirm and amend:"
        )
        for name in names:
            si, bl = _si_bl(by_field.get(name))
            label = FIELD_LABEL.get(name, name)
            lines.append(f"- {label}: SI is “{si}”; BL draft is “{bl}”")
        if not names:
            lines.append("- (see attached compare)")
        return "\n".join(lines) + SIGN

    if verdict == "CLEAR" or st == "OK":
        return (
            f"Regarding '{subject or 'this booking'}': the seven compare fields match the SI. "
            "You may proceed. Optional human spot-check welcome." + SIGN
        )

    if verdict == "PILOT" or st == "NEEDS_REVIEW":
        reason = review_reason or ""
        if reason == ReviewReason.MISSING_ATTACHMENT.value or "missing_attachment" in reason:
            ask = "Please re-attach both the SI and the draft BL."
        elif reason == ReviewReason.WRONG_DOC_TYPE.value or "wrong_doc_type" in reason:
            ask = "The attachment is the wrong document type. Please send the draft BL."
        elif reason == ReviewReason.UNREADABLE.value or "unreadable" in reason:
            ask = "The file cannot be read. Please resend a searchable PDF or text copy."
        elif reason == ReviewReason.MISSING_VALUE.value or "missing_value" in reason:
            ask = "Some fields are blank placeholders. Please complete them and resend."
        else:
            ask = "This file is with a human operator. We will confirm shortly."
        return f"Regarding '{subject or 'this booking'}': {ask}" + SIGN

    return None


def generate_outbox_from_run(run: dict, verdict: str) -> str | None:
    payload = run.get("payload") or {}
    card = payload.get("card") or {}
    official = payload.get("official") or {}
    return generate_outbox_message(
        subject=card.get("subject") or "",
        category=official.get("category"),
        status=official.get("status"),
        review_reason=official.get("review_reason"),
        defect_fields=official.get("defect_fields") or [],
        field_verdicts=card.get("field_verdicts") or [],
        bridge_verdict=verdict,
    )


def english_reply_draft(payload: dict, verdict: str | None = None) -> str | None:
    """Serve English-only Outbox copy; rewrite any legacy bilingual drafts on read."""
    card = payload.get("card") if isinstance(payload, dict) else {}
    if not isinstance(card, dict):
        card = {}
    draft = card.get("reply_draft") or ""
    if draft and not contains_cjk(draft):
        return draft[:2500]
    fresh = generate_outbox_from_run(
        {"payload": payload},
        (verdict or card.get("verdict") or ""),
    )
    if fresh:
        card["reply_draft"] = fresh
    return ((fresh or draft) or "")[:2500] or None


# Back-compat alias used by the Bridge API.
ensure_english_reply_draft = english_reply_draft


def draft_reply(card: CaseCard) -> str:
    _ = load_prompt("draft_reply.md")
    official = card.official
    text = generate_outbox_message(
        subject=card.subject,
        category=official.category.value if official else None,
        status=official.status.value if official and official.status else None,
        review_reason=official.review_reason.value if official and official.review_reason else None,
        defect_fields=list(official.defect_fields) if official else [],
        field_verdicts=card.field_verdicts,
        bridge_verdict=card.verdict.value,
    )
    return text or (
        f"Regarding '{card.subject or card.email_id}': filed. No operator reply required." + SIGN
    )
