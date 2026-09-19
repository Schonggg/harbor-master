#!/usr/bin/env python3
"""Debug: which Scout rule branch fires on the official 520.

Not part of the product. Safe to delete after the SI_REQUEST / BL_COMPARISON fix.
Reads local data/sdoc/inbox JSON only. Does not read ground truth.

  py -3 scripts/debug_scout_si_bl.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harbormaster.ingest.loader_adapter import coerce_email  # noqa: E402
from harbormaster.models import Category, EmailMessage  # noqa: E402
from harbormaster.scout import rules as R  # noqa: E402
from harbormaster.scout.rules import official_rule_classify, rule_classify  # noqa: E402
from harbormaster.scout.router import ScoutRouter  # noqa: E402

INBOX = ROOT / "data" / "sdoc" / "inbox"


def _clip(text: str, n: int = 280) -> str:
    one = re.sub(r"\s+", " ", (text or "")).strip()
    return one[:n] + ("…" if len(one) > n else "")


def branch_official(email: EmailMessage) -> tuple[str, str | None]:
    """Mirror official_rule_classify if/elif order with named branches."""
    blob = R._blob(email)
    has_si, has_bl = R._attachment_kinds(email)
    si_pat = R._si_request_text(blob)
    bl_pat = bool(R._BL_COMPARE.search(blob))

    if R._SPAM.search(blob) and not has_si and not has_bl and not R._INVOICE.search(blob):
        return "spam", "SPAM"
    if has_si and has_bl:
        return "si+bl attachments", "BL_COMPARISON"
    if bl_pat:
        return "bl-comparison language", "BL_COMPARISON"
    if si_pat:
        return "si-request", "SI_REQUEST"
    if R._INVOICE.search(blob) and not has_si:
        return "invoice", "INVOICE_QUERY"
    if R._GENERAL.search(blob) and not has_si and not has_bl:
        return "general-ops", "GENERAL"
    if has_si and not has_bl and R._HAS_SI.search(email.subject):
        return "si-only", "SI_REQUEST"
    return "none", None


def si_would_match(email: EmailMessage) -> bool:
    blob = R._blob(email)
    if R._SI_REQUEST.search(blob) or len(R._FIELD_LIST.findall(blob)) >= 2:
        return True
    has_si, has_bl = R._attachment_kinds(email)
    return bool(has_si and not has_bl and R._HAS_SI.search(email.subject))


def bl_language_hit(email: EmailMessage) -> str | None:
    m = R._BL_COMPARE.search(R._blob(email))
    return m.group(0) if m else None


def load_local(path: Path) -> EmailMessage:
    data = json.loads(path.read_text(encoding="utf-8"))
    return coerce_email(data, email_id=path.stem)


def main() -> None:
    paths = sorted(INBOX.glob("email_*.json"))
    if not paths:
        raise SystemExit(f"no emails in {INBOX}")
    router = ScoutRouter(degrade=True)
    cats: Counter[str] = Counter()
    branches: Counter[str] = Counter()
    swallowed: list[dict] = []
    si_hits: list[dict] = []
    below_floor = 0
    att_only_si: list[dict] = []

    for path in paths:
        email = load_local(path)
        branch, cat = branch_official(email)
        ruled = official_rule_classify(email)
        routed = router.route(email)
        full = rule_classify(email)
        cats[routed.category.value] += 1
        branches[f"{branch} -> {cat or 'FALLTHROUGH'}"] += 1
        if ruled and ruled.confidence < 0.95:
            below_floor += 1
        row = {
            "email_id": email.email_id,
            "branch": branch,
            "official_rule": ruled.category.value if ruled else None,
            "official_reason": ruled.reason if ruled else None,
            "rule_classify": full.category.value if full else None,
            "routed": routed.category.value,
            "subject": email.subject,
            "si_would": si_would_match(email),
            "bl_span": bl_language_hit(email),
            "has_si_bl": R._attachment_kinds(email),
            "n_att": len(email.attachments) or len(email.attachment_paths),
            "body": _clip(email.body_text, 320),
        }
        if branch in {"si+bl attachments", "bl-comparison language", "bl+si mentions"} and si_would_match(
            email
        ):
            swallowed.append(row)
        if branch == "si+bl attachments" and si_would_match(email) and not bl_language_hit(email):
            att_only_si.append(row)
        if routed.category == Category.SI_REQUEST:
            si_hits.append(row)

    print(f"emails {len(paths)}")
    print("routed (rules-only ScoutRouter):")
    for k, n in cats.most_common():
        print(f"  {k:20} {n}")
    print("official_rule_classify branches:")
    for k, n in branches.most_common():
        print(f"  {n:4}  {k}")
    print(f"SI_REQUEST routed: {len(si_hits)}")
    print(f"rules fired below 0.95 floor: {below_floor}")
    print(f"BL branch fired AND SI_REQUEST pattern also matched: {len(swallowed)}")
    print(f"  of those, si+bl attachments with NO compare language: {len(att_only_si)}")

    print("\n--- up to 5 swallowed samples (prefer attachment-only) ---")
    shown = att_only_si[:5] if att_only_si else swallowed[:5]
    if not att_only_si and swallowed:
        shown = swallowed[:5]
    elif att_only_si and len(att_only_si) < 5:
        extra = [r for r in swallowed if r not in att_only_si][: 5 - len(att_only_si)]
        shown = att_only_si + extra
    for row in shown[:5]:
        print(
            json.dumps(
                {
                    "email_id": row["email_id"],
                    "branch": row["branch"],
                    "bl_span": row["bl_span"],
                    "has_si_bl": row["has_si_bl"],
                    "subject": row["subject"],
                    "body": row["body"],
                },
                ensure_ascii=False,
            )
        )

    print("\n--- up to 8 SI_REQUEST routed ---")
    for row in si_hits[:8]:
        print(
            json.dumps(
                {
                    "email_id": row["email_id"],
                    "branch": row["branch"],
                    "subject": row["subject"],
                    "body": row["body"],
                },
                ensure_ascii=False,
            )
        )

    print("\n--- BL language spans among swallowed (top 15) ---")
    spans = Counter((r["bl_span"] or "(attachments only)") for r in swallowed)
    for k, n in spans.most_common(15):
        print(f"  {n:4}  {k!r}")


if __name__ == "__main__":
    main()
