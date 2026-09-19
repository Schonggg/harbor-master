#!/usr/bin/env python3
"""Debug: why official NEEDS_REVIEW fires on the local 520.

Reads data/sdoc/inbox only. Does not import organizer ground truth.
Does not write data/submission.json.

  py -3 scripts/debug_needs_review.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harbormaster.graph import nodes  # noqa: E402
from harbormaster.graph.state import PipelineState  # noqa: E402
from harbormaster.ingest.loader_adapter import coerce_email  # noqa: E402
from harbormaster.models import ComparisonStatus, EmailMessage  # noqa: E402
from harbormaster.official.gate import (  # noqa: E402
    _COMPARE,
    _MISSING,
    _SEND,
    claims_attachment_missing,
    scene_a_skip_missing_attachment,
)

INBOX = ROOT / "data" / "sdoc" / "inbox"
BUNDLE = ROOT / "data" / "sdoc"
CALIBRATION_CANDIDATES = [
    ROOT / "data" / "calibration.json",
    ROOT / "data" / "sdoc" / "calibration.json",
    ROOT / "reports" / "calibration.json",
    ROOT / "data" / "sdoc" / "expected_verdicts.json",
]


def _clip(text: str, n: int = 240) -> str:
    one = re.sub(r"\s+", " ", (text or "")).strip()
    return one[:n] + ("..." if len(one) > n else "")


def _resolve(path_str: str) -> str:
    path = Path(path_str)
    if path.is_file():
        return str(path)
    for root in (BUNDLE, INBOX, INBOX.parent):
        cand = root / path_str
        if cand.is_file():
            return str(cand)
        named = root / "attachments" / Path(path_str).name
        if named.is_file():
            return str(named)
    return path_str


def load_local(path: Path) -> EmailMessage:
    data = json.loads(path.read_text(encoding="utf-8"))
    email = coerce_email(data, email_id=path.stem)
    email.attachment_paths = [_resolve(p) for p in email.attachment_paths]
    for att in email.attachments:
        att.local_path = _resolve(att.local_path or att.path)
        att.path = att.local_path or att.path
    return email


def load_calibration() -> dict[str, dict]:
    for path in CALIBRATION_CANDIDATES:
        if not path.is_file():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "emails" in raw and isinstance(raw["emails"], dict):
            raw = raw["emails"]
        if not isinstance(raw, dict):
            continue
        out = {}
        for key, rec in raw.items():
            if isinstance(rec, dict) and ("status" in rec or "review_reason" in rec):
                out[str(key)] = rec
        if out:
            return {"path": str(path), "rows": out}
    return {}


def run_one(email: EmailMessage) -> PipelineState:
    state = PipelineState(
        email=email,
        degrade=True,
        rules_only=True,
        two_value=True,
        save_board=False,
    )
    for step in (nodes.node_chaos, nodes.node_scout, nodes.node_reader, nodes.node_court):
        state = step(state)
    return state


def signal_of(email: EmailMessage, state: PipelineState) -> str:
    blob = f"{email.subject}\n{email.body_text}"
    official = state.official
    n_att = len(email.attachments) or len(email.attachment_paths)
    existing = sum(1 for p in email.attachment_paths if Path(p).is_file())
    send_m = _SEND.search(blob)
    cmp_m = _COMPARE.search(blob)
    miss_m = _MISSING.search(blob)
    kinds = [(d.filename, d.kind, d.parser_used, len((d.text or "").strip())) for d in state.docs]
    parts = [
        f"n_att={n_att}",
        f"files_on_disk={existing}",
        f"docs={kinds!r}",
        f"scene_a={scene_a_skip_missing_attachment(email)}",
        f"claims_missing={claims_attachment_missing(email)}",
        f"send={send_m.group(0)!r}" if send_m else "send=None",
        f"compare={cmp_m.group(0)!r}" if cmp_m else "compare=None",
        f"missing_claim={miss_m.group(0)!r}" if miss_m else "missing_claim=None",
        f"scout={state.scout.category.value if state.scout else None}",
        f"status={official.status.value if official and official.status else None}",
        f"category={official.category.value if official else None}",
    ]
    if state.health:
        parts.append(f"health.detail={state.health.detail!r}")
        if state.health.missing_fields:
            parts.append("fields=" + ",".join(state.health.missing_fields))
        parts.append(f"si={state.health.si_filename!r} bl={state.health.bl_filename!r}")
    return " | ".join(parts)


def main() -> None:
    paths = sorted(INBOX.glob("email_*.json"))
    if not paths:
        raise SystemExit(f"no emails in {INBOX}")

    reasons: Counter[str] = Counter()
    status_by_cat: Counter[str] = Counter()
    rows: list[dict] = []
    by_reason: dict[str, list[dict]] = defaultdict(list)

    for path in paths:
        email = load_local(path)
        state = run_one(email)
        official = state.official
        cat = official.category.value if official else "?"
        status = official.status.value if official and official.status else "null"
        status_by_cat[f"{cat}:{status}"] += 1
        if not official or official.status != ComparisonStatus.NEEDS_REVIEW:
            continue
        reason = official.review_reason.value if official.review_reason else "none"
        reasons[reason] += 1
        row = {
            "email_id": email.email_id,
            "review_reason": reason,
            "category": cat,
            "subject": email.subject,
            "body": _clip(email.body_text, 280),
            "signal": signal_of(email, state),
            "n_att": len(email.attachment_paths),
            "scene_a": scene_a_skip_missing_attachment(email),
        }
        rows.append(row)
        by_reason[reason].append(row)

    print(f"emails {len(paths)}")
    print(f"NEEDS_REVIEW {len(rows)}")
    print()
    print("review_reason counts:")
    for key in ("missing_attachment", "wrong_doc_type", "unreadable", "missing_value"):
        print(f"  {key}: {reasons.get(key, 0)} 次")
    extra = [k for k in reasons if k not in {"missing_attachment", "wrong_doc_type", "unreadable", "missing_value"}]
    for key in extra:
        print(f"  {key}: {reasons[key]} 次")

    print()
    print("official status by category:")
    for k, n in status_by_cat.most_common():
        print(f"  {n:4}  {k}")

    print()
    print("NEEDS_REVIEW by scout/official category:")
    cat_n = Counter(r["category"] for r in rows)
    for k, n in cat_n.most_common():
        print(f"  {n:4}  {k}")

    calib = load_calibration()
    if calib:
        print()
        print(f"calibration file: {calib['path']} n={len(calib['rows'])}")
        gold = calib["rows"]
        for reason, items in by_reason.items():
            fp = 0
            for row in items:
                g = gold.get(row["email_id"])
                if not g:
                    continue
                gold_status = g.get("status")
                gold_reason = g.get("review_reason")
                if gold_status in {"OK", "MISMATCH"} or (
                    gold_status == "NEEDS_REVIEW" and gold_reason and gold_reason != reason
                ):
                    fp += 1
            print(f"  {reason}: predicted {len(items)}, gold-disagree (likely FP) {fp}")
    else:
        print()
        print("calibration: none found (looked for data/calibration.json etc.; did not read organizer ground_truth)")
        print("heuristic likely-false-alarm (scene A skip true, or zero attachments without a missing-file claim):")
        for reason, items in by_reason.items():
            likely = [
                r
                for r in items
                if r["scene_a"]
                or (r["n_att"] == 0 and "missing_claim=None" in r["signal"] and reason == "missing_attachment")
            ]
            print(f"  {reason}: {len(likely)}/{len(items)} look like false alarms")

    print()
    print("--- typical NEEDS_REVIEW samples (up to 8) ---")
    shown = 0
    order = ["missing_attachment", "missing_value", "wrong_doc_type", "unreadable"]
    for reason in order:
        for row in by_reason.get(reason, [])[:3]:
            print(
                json.dumps(
                    {
                        "email_id": row["email_id"],
                        "review_reason": row["review_reason"],
                        "category": row["category"],
                        "scene_a": row["scene_a"],
                        "signal": row["signal"],
                        "subject": row["subject"],
                        "body": row["body"],
                    },
                    ensure_ascii=False,
                )
            )
            shown += 1
            if shown >= 8:
                break
        if shown >= 8:
            break


if __name__ == "__main__":
    main()
