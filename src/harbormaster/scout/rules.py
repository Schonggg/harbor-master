"""Cheap keyword/heuristic pre-filter for the five official categories."""

from __future__ import annotations

import re

from harbormaster.models import (
    CATEGORY_TO_SCOUT,
    SCOUT_TO_CATEGORY,
    Category,
    EmailMessage,
    ScoutLabel,
    ScoutResult,
)


_SPAM = re.compile(
    r"\b(unsubscribe|out of office|marketing rates|click here|congratulations you|"
    r"lottery|crypto giveaway|viagra|work from home|cheap freight promo|"
    r"won\b|gift card|claim now|verify your account|limited time offer|"
    r"guaranteed returns|urgent:\s*your email storage)\b",
    re.I,
)
_INVOICE = re.compile(
    r"\b(invoice|debit note|credit note|freight charges|thc\b|demurrage|detention|"
    r"payment query|overcharged|double.?charg|cancel invoice|billing|"
    r"goods receipt|\bgr\b|d&d|local charge)\b",
    re.I,
)
# Comparison only — never a bare "draft BL" / "SI" mention, and never the
# SI_REQUEST closer "Please revert with draft BL once available."
_BL_COMPARE = re.compile(
    r"("
    r"si\s*vs\.?\s*b/?l|b/?l\s*vs\.?\s*si|"
    r"compare.{0,60}(?:si|shipping instruction).{0,40}(?:b/?l|bill of lading)|"
    r"compare.{0,60}(?:b/?l|bill of lading).{0,40}(?:si|shipping instruction)|"
    r"(?:check|verify) the draft b/?l against|"
    r"(?:confirm|verify) the (?:draft )?b/?l matches|"
    r"verify the (?:draft )?b/?l|"
    r"please (?:check|verify|confirm|reconcile).{0,40}(?:b/?l|bill of lading)|"
    r"(?:check|verify|confirm|reconcile).{0,30}(?:si|shipping instruction)"
    r".{0,30}(?:against|vs\.?|with).{0,20}(?:b/?l|bill of lading)|"
    r"(?:send|provide|share|assist to send).{0,50}(?:draft )?b/?l.{0,40}(?:for )?check|"
    r"confirm (?:the )?(?:draft )?b/?l is in order|"
    r"\bto confirm docs\b|"
    r"request bl draft"
    r")",
    re.I,
)
_SI_REQUEST = re.compile(
    r"\b((?:please |kindly )?(?:send|issue|prepare|provide|need|request|find).{0,40}"
    r"(?:shipping instruction|\bSI\b)|"
    r"\bSI\b.{0,20}(needed|required|request)|"
    r"(?:request|needed)\s+SI\b|"
    r"new shipping instruction|missing (?:the )?SI)\b",
    re.I,
)
_GENERAL = re.compile(
    r"\b(automated notification|rpa bot|berthing report|outstanding bl list|"
    r"happy holidays|season.?s greetings|merry christmas|this is an automated|"
    r"\bsla\b)\b",
    re.I,
)
_FIELD_LIST = re.compile(r"\b(pol|pod|shipper|consignee)\s*:", re.I)
_HAS_SI = re.compile(r"\b(shipping instruction|\bSI\b)\b", re.I)

# Bridge-only finer labels (do not leak "unknown" into official category)
_DEMO_LABELS: list[tuple[ScoutLabel, re.Pattern[str]]] = [
    (ScoutLabel.BOOKING_CONFIRMATION, re.compile(r"\bbooking\s+(confirm|ref|space is confirmed)\b", re.I)),
    (ScoutLabel.AMENDMENT_REQUEST, re.compile(r"\b(amend|amendment|correction)\b", re.I)),
    (ScoutLabel.DISCREPANCY_QUERY, re.compile(r"\b(discrepan|mismatch|not match)\b", re.I)),
    (ScoutLabel.SHIPPING_INSTRUCTION, re.compile(r"\b(shipping instruction|\bSI\b)", re.I)),
    (ScoutLabel.BILL_OF_LADING, re.compile(r"\b(bill of lading|\bB/?L\b|BL draft)", re.I)),
    (ScoutLabel.INVOICE_OR_CHARGES, re.compile(r"\b(invoice|debit note|freight charges)\b", re.I)),
    (ScoutLabel.OPERATIONAL_NOISE, re.compile(r"\b(unsubscribe|out of office|marketing rates)\b", re.I)),
]


def _blob(email: EmailMessage) -> str:
    names = " ".join(a.filename or a.path for a in email.attachments)
    names += " " + " ".join(email.attachment_paths)
    return f"{email.subject}\n{email.body_text}\n{names}"


def _attachment_kinds(email: EmailMessage) -> tuple[bool, bool]:
    has_si = False
    has_bl = False
    for att in email.attachments:
        hint = (att.kind_hint or "").lower()
        name = f"{att.filename} {att.path}".lower()
        if hint == "si" or "shipping" in name or "_si." in name or "-si." in name or re.search(r"\bsi\b", name):
            has_si = True
        if hint == "bl" or "lading" in name or "_bl." in name or "-bl." in name or re.search(r"\bbl\b", name) or "bol" in name:
            has_bl = True
    for path in email.attachment_paths:
        name = path.lower()
        if "shipping" in name or "_si." in name or "-si." in name or re.search(r"\bsi\b", name):
            has_si = True
        if "lading" in name or "_bl." in name or "-bl." in name or re.search(r"\bbl\b", name) or "bol" in name:
            has_bl = True
    body = email.body_text
    if "=== SHIPPING INSTRUCTION" in body:
        has_si = True
    if "=== BILL OF LADING" in body:
        has_bl = True
    return has_si, has_bl


def _si_request_text(blob: str) -> bool:
    return bool(_SI_REQUEST.search(blob) or len(_FIELD_LIST.findall(blob)) >= 2)


def official_rule_classify(email: EmailMessage) -> ScoutResult | None:
    blob = _blob(email)
    has_si, has_bl = _attachment_kinds(email)
    bl_compare = bool(_BL_COMPARE.search(blob))
    si_text = _si_request_text(blob)

    if _SPAM.search(blob) and not has_si and not has_bl and not _INVOICE.search(blob):
        return ScoutResult(
            category=Category.SPAM,
            label=ScoutLabel.OPERATIONAL_NOISE,
            confidence=0.96,
            reason="rule:spam",
            route="rules",
        )
    if has_si and has_bl:
        return ScoutResult(
            category=Category.BL_COMPARISON,
            label=ScoutLabel.BILL_OF_LADING,
            confidence=0.97,
            reason="rule:si+bl attachments",
            route="rules",
        )
    if bl_compare:
        return ScoutResult(
            category=Category.BL_COMPARISON,
            label=ScoutLabel.BILL_OF_LADING,
            confidence=0.95,
            reason="rule:bl-comparison language",
            route="rules",
        )
    # SI_REQUEST before invoice: SI bodies often list "Original invoice" as a
    # required document, which must not steal the field-list SI branch.
    if si_text:
        return ScoutResult(
            category=Category.SI_REQUEST,
            label=ScoutLabel.SHIPPING_INSTRUCTION,
            confidence=0.96,
            reason="rule:si-request",
            route="rules",
        )
    if _INVOICE.search(blob) and not has_si:
        return ScoutResult(
            category=Category.INVOICE_QUERY,
            label=ScoutLabel.INVOICE_OR_CHARGES,
            confidence=0.94,
            reason="rule:invoice",
            route="rules",
        )
    if _GENERAL.search(blob) and not has_si and not has_bl:
        return ScoutResult(
            category=Category.GENERAL,
            label=ScoutLabel.OPERATIONAL_NOISE,
            confidence=0.9,
            reason="rule:general-ops",
            route="rules",
        )
    if has_si and not has_bl and _HAS_SI.search(email.subject):
        return ScoutResult(
            category=Category.SI_REQUEST,
            label=ScoutLabel.SHIPPING_INSTRUCTION,
            confidence=0.95,
            reason="rule:si-only",
            route="rules",
        )
    return None
    # Macro-F1 weights SPAM/GENERAL equally with BL_COMPARISON — calibrate each
    # category on its own, never only the overall accuracy.


def demo_label(email: EmailMessage) -> ScoutLabel | None:
    blob = _blob(email)
    tag = (email.meta or {}).get("tag")
    if tag:
        try:
            return ScoutLabel(str(tag))
        except ValueError:
            pass
    if not blob.strip() and not email.attachment_paths and not email.attachments:
        return ScoutLabel.UNKNOWN
    for label, pattern in _DEMO_LABELS:
        if pattern.search(blob):
            return label
    return None


_MENTION_ONLY = {
    ScoutLabel.SHIPPING_INSTRUCTION,
    ScoutLabel.BILL_OF_LADING,
    ScoutLabel.DISCREPANCY_QUERY,
}


def rule_classify(email: EmailMessage) -> ScoutResult | None:
    """Official category first; Bridge scout label is a parallel view."""
    official = official_rule_classify(email)
    label = demo_label(email)
    if official:
        if label and label != ScoutLabel.UNKNOWN:
            return official.model_copy(update={"label": label})
        return official
    if label in _MENTION_ONLY:
        # A bare SI/BL/discrepancy mention is not an official SI_REQUEST or
        # BL_COMPARISON. Those categories only come from official_rule_classify.
        return ScoutResult(
            category=Category.GENERAL,
            label=label,
            confidence=0.9,
            reason=f"rule:demo-label:{label.value}",
            route="rules",
        )
    if label:
        return ScoutResult(
            category=SCOUT_TO_CATEGORY.get(label, Category.GENERAL),
            label=label,
            confidence=0.9 if label != ScoutLabel.UNKNOWN else 1.0,
            reason=f"rule:demo-label:{label.value}",
            route="rules",
        )
    return None


def commit_category(result: ScoutResult) -> ScoutResult:
    """Never emit an empty/unknown official category."""
    if result.category:
        if result.label == ScoutLabel.UNKNOWN:
            return result.model_copy(update={"label": CATEGORY_TO_SCOUT[result.category]})
        return result
    category = SCOUT_TO_CATEGORY.get(result.label, Category.GENERAL)
    return result.model_copy(update={"category": category, "label": result.label or CATEGORY_TO_SCOUT[category]})
