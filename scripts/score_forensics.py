#!/usr/bin/env python3
"""Compare submission.json to organizer ground_truth.json.

Development-only. Pipeline code under src/harbormaster does not import gold labels.

    py -3 scripts/score_forensics.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from sdoc_paths import find_gold  # noqa: E402

FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)


def _load(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "emails" in raw and isinstance(raw["emails"], dict):
        raw = raw["emails"]
    if not isinstance(raw, dict):
        raise SystemExit(f"unexpected JSON shape in {path}")
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def _fields(rec: dict) -> list[str]:
    values = rec.get("defect_fields") or []
    return [str(x) for x in values]


def _fail_stage(gold: dict, pred: dict) -> str:
    g_cat = gold.get("category")
    p_cat = pred.get("category")
    if g_cat != p_cat:
        return "classification"
    if gold.get("status") == "NEEDS_REVIEW" and pred.get("status") != "NEEDS_REVIEW":
        return "review-gate"
    if pred.get("status") == "NEEDS_REVIEW" and gold.get("status") != "NEEDS_REVIEW":
        return "review-gate"
    if gold.get("has_defect") and not pred.get("has_defect"):
        if pred.get("status") == "NEEDS_REVIEW":
            return "review-gate"
        return "defect detection"
    if set(_fields(gold)) != set(_fields(pred)):
        return "defect field identification"
    if gold.get("status") != pred.get("status"):
        return "decision routing"
    return "other"


def main() -> None:
    gold_path = find_gold()
    sub_path = ROOT / "data" / "submission.json"
    if not gold_path:
        print(
            "ground_truth.json not found. Place sdoc-hackathon-docker beside the repo "
            "or set SDOC_GROUND_TRUTH. No forensics without gold."
        )
        raise SystemExit(2)
    if not sub_path.is_file():
        print(f"missing {sub_path}; run py -3 scripts/benchmark_official.py first")
        raise SystemExit(2)

    gold = _load(gold_path)
    pred = _load(sub_path)
    ids = sorted(set(gold) | set(pred))

    confusion = Counter()
    e2e_fail: list[dict] = []
    true_esc: list[str] = []
    false_esc: list[str] = []
    missed_esc: list[str] = []
    field_err = Counter()
    stages = Counter()

    gold_defect_ids = [
        eid
        for eid, rec in gold.items()
        if rec.get("has_defect") or rec.get("status") == "MISMATCH"
    ]
    caught = 0
    for eid in gold_defect_ids:
        g = gold[eid]
        p = pred.get(eid) or {}
        gold_set = set(_fields(g))
        pred_set = set(_fields(p))
        covered = (
            p.get("category") == "BL_COMPARISON"
            and g.get("category") == "BL_COMPARISON"
            and bool(p.get("has_defect"))
            and gold_set <= pred_set
        )
        if covered:
            caught += 1
            continue
        row = {
            "email_id": eid,
            "gold_category": g.get("category"),
            "predicted_category": p.get("category"),
            "gold_decision": g.get("status"),
            "predicted_decision": p.get("status"),
            "gold_defects": _fields(g),
            "predicted_defects": _fields(p),
            "suspected_failure_stage": _fail_stage(g, p),
        }
        e2e_fail.append(row)
        stages[row["suspected_failure_stage"]] += 1

    for eid in ids:
        g = gold.get(eid) or {}
        p = pred.get(eid) or {}
        confusion[(g.get("category") or "?", p.get("category") or "?")] += 1
        g_nr = g.get("status") == "NEEDS_REVIEW"
        p_nr = p.get("status") == "NEEDS_REVIEW"
        if g_nr and p_nr:
            true_esc.append(eid)
        elif p_nr and not g_nr:
            false_esc.append(eid)
        elif g_nr and not p_nr:
            missed_esc.append(eid)
        for field in set(_fields(g)) ^ set(_fields(p)):
            if field in FIELDS:
                field_err[field] += 1
            else:
                field_err["other"] += 1

    report = {
        "gold": str(gold_path),
        "submission": str(sub_path),
        "emails": len(ids),
        "classification_confusion": {
            f"{g} -> {p}": n for (g, p), n in sorted(confusion.items(), key=lambda kv: (-kv[1], kv[0]))
        },
        "end_to_end": {
            "gold_defect_emails": len(gold_defect_ids),
            "caught": caught,
            "failures": e2e_fail,
            "failure_stages": dict(stages),
        },
        "needs_review": {
            "gold": sum(1 for rec in gold.values() if rec.get("status") == "NEEDS_REVIEW"),
            "predicted": sum(1 for rec in pred.values() if rec.get("status") == "NEEDS_REVIEW"),
            "true_escalations": true_esc,
            "false_escalations": false_esc,
            "missed_escalations": missed_esc,
        },
        "defect_field_errors": dict(field_err),
    }

    out = ROOT / "reports" / "score_forensics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Classification confusion (gold -> predicted)")
    for (g, p), n in sorted(confusion.items(), key=lambda kv: (-kv[1], kv[0])):
        if g != p:
            print(f"  {n:4}  {g} -> {p}")
    print()
    print(f"E2E failures: {len(e2e_fail)} / {len(gold_defect_ids)} gold defect emails (caught {caught})")
    for key, n in stages.most_common():
        print(f"  {key}: {n}")
    print()
    print("NEEDS_REVIEW")
    print(f"  true escalations:   {len(true_esc)}")
    print(f"  false escalations:  {len(false_esc)}")
    print(f"  missed escalations: {len(missed_esc)}")
    print()
    print("Defect field disagreements")
    for field, n in field_err.most_common():
        print(f"  {field}: {n}")
    print()
    print("--- E2E failures ---")
    for row in e2e_fail:
        print(json.dumps(row, ensure_ascii=False))
    print()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
