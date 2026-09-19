"""Outbox: turn a verdict into a sendable reply. Never auto-sent.

This is product copy, not scoring. Defect fields still come only from L5/assemble.
"""

from __future__ import annotations

from typing import Any

from harbormaster.config import load_prompt
from harbormaster.models import CaseCard, ReviewReason

FIELD_CN = {
    "shipper": "发货人 / Shipper",
    "consignee": "收货人 / Consignee",
    "notify_party": "通知方 / Notify Party",
    "port_of_loading": "装货港 / POL",
    "port_of_discharge": "卸货港 / POD",
    "container_count": "箱量 / Containers",
    "gross_weight_kg": "毛重 / Gross weight",
}

SIGN = "\n\n[操作员姓名] / Harbormaster Desk"


def _looks_zh(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))


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
    """Professional reply for the operator to send. None if the mail is only archived."""
    blob = f"{subject}\n{body}"
    zh = _looks_zh(blob)
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
        if zh:
            lines.append(f"关于「{subject or '本票单据'}」：经核对，以下字段与 SI 不符，烦请确认并更正：")
        else:
            lines.append(
                f"Regarding '{subject or 'this booking'}': the draft BL does not match the SI on the fields below. Please confirm and amend:"
            )
        for name in names:
            si, bl = _si_bl(by_field.get(name))
            label = FIELD_CN.get(name, name)
            if zh:
                lines.append(f"- {label}：SI 为「{si}」，BL 草稿为「{bl}」")
            else:
                lines.append(f"- {label}: SI is “{si}”; BL draft is “{bl}”")
        if not names:
            lines.append("- (see attached compare)")
        return "\n".join(lines) + SIGN

    if verdict == "CLEAR" or st == "OK":
        if zh:
            return (
                f"关于「{subject or '本票单据'}」：七个核心字段已与 SI 核对一致，可以放行。"
                "如需抽查，请回复本邮件。" + SIGN
            )
        return (
            f"Regarding '{subject or 'this booking'}': the seven compare fields match the SI. "
            "You may proceed. Optional human spot-check welcome." + SIGN
        )

    if verdict == "PILOT" or st == "NEEDS_REVIEW":
        reason = review_reason or ""
        if reason == ReviewReason.MISSING_ATTACHMENT.value or "missing_attachment" in reason:
            ask = "请补发 SI 与 BL 草稿附件。" if zh else "Please re-attach both the SI and the draft BL."
        elif reason == ReviewReason.WRONG_DOC_TYPE.value or "wrong_doc_type" in reason:
            ask = "附件类型不对，请改发正确的 BL 草稿。" if zh else "The attachment is the wrong document type. Please send the draft BL."
        elif reason == ReviewReason.UNREADABLE.value or "unreadable" in reason:
            ask = "文件无法打开或没有文本层，请重新发送可检索的 PDF/文本。" if zh else "The file cannot be read. Please resend a searchable PDF or text copy."
        elif reason == ReviewReason.MISSING_VALUE.value or "missing_value" in reason:
            ask = "部分字段为空白/占位符，请补全后再发。" if zh else "Some fields are blank placeholders. Please complete them and resend."
        else:
            ask = "本票已交人工复核，我们会尽快回复。" if zh else "This file is with a human operator. We will confirm shortly."
        head = f"关于「{subject or '本票单据'}」：" if zh else f"Regarding '{subject or 'this booking'}': "
        return head + ask + SIGN

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
