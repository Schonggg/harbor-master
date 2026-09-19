"""L2 structural gate — four NEEDS_REVIEW signals, including scene A.

Hit any signal and short-circuit: do not compare, even if some text was readable.
"""

from __future__ import annotations

import re

from harbormaster.models import EmailMessage

_COMPARE = re.compile(
    r"\b(compare|check the draft|confirm the (?:details|bl|draft)|verify the bl matches)\b",
    re.I,
)
_MISSING = re.compile(
    r"\b(still missing|dropped|not received|yet to be attached|will not open|"
    r"attachment (?:is )?missing|haven't (?:received|got) the)\b",
    re.I,
)
_SEND = re.compile(
    r"\b((?:please |kindly )?(?:send|prepare|issue|provide) (?:us )?(?:the )?(?:draft )?(?:bl|si|b/?l)|"
    r"need you to send|please send)\b",
    re.I,
)
_PLACEHOLDERS = {
    "???",
    "tba",
    "tbc",
    "t.b.a",
    "t.b.a.",
    "n/a",
    "n.a",
    "n.a.",
    "nil",
    "unknown",
    "not known",
    "not applicable",
    "-",
    "--",
}
_BLANK = re.compile(r"^_+\s*[a-zA-Z%]*$")


def is_placeholder(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    if text.casefold() in _PLACEHOLDERS:
        return True
    return bool(_BLANK.match(text))


def scene_a_skip_missing_attachment(email: EmailMessage) -> bool:
    """True when the mail asks the other party to send files — not a missing-attachment defect."""
    blob = f"{email.subject}\n{email.body_text}"
    if _COMPARE.search(blob) and _MISSING.search(blob):
        return False
    return bool(_SEND.search(blob)) and not _COMPARE.search(blob)


def claims_attachment_missing(email: EmailMessage) -> bool:
    blob = f"{email.subject}\n{email.body_text}"
    return bool(_COMPARE.search(blob) and _MISSING.search(blob))
