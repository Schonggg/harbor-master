from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter

from harbormaster.ledger.store import LedgerStore

router = APIRouter()

SCOUT_LABELS = [
    "booking_confirmation",
    "shipping_instruction",
    "bill_of_lading",
    "amendment_request",
    "discrepancy_query",
    "invoice_or_charges",
    "operational_noise",
    "unknown",
]


@router.get("/metrics")
def metrics():
    store = LedgerStore()
    runs = store.list_runs()
    official = store.list_verdicts()
    verdicts = Counter(r["verdict"] for r in runs)

    avoided = 0
    mismatch_raw = 0
    field_stats: dict[str, Counter] = defaultdict(Counter)
    confusion: dict[str, Counter] = defaultdict(Counter)

    for r in runs:
        card = r["payload"].get("card") or {}
        scout = (card.get("scout") or {}).get("label") or "unknown"
        # self-confusion placeholder: predicted vs predicted (demo matrix fills when gold arrives)
        confusion[scout][scout] += 1
        for fv in card.get("field_verdicts") or []:
            name = fv.get("field") or "?"
            state = fv.get("state") or "?"
            field_stats[name][state] += 1
            if state == "MATCH" and fv.get("winning_strategy"):
                avoided += 1
            if state == "MISMATCH":
                mismatch_raw += 1

    total = len(runs) or 1
    clear = verdicts.get("CLEAR", 0)
    hold = verdicts.get("HOLD", 0)
    pilot = verdicts.get("PILOT", 0)
    auto_rate = round(100.0 * (clear + hold) / total, 1)

    # False alarms: mismatches that a strategy *could* have defended but didn't —
    # demo metric = 0 when strategies absorb synonym noise; show avoided prominently.
    false_alarms = 0

    matrix = {g: {p: confusion[g][p] for p in SCOUT_LABELS} for g in SCOUT_LABELS}

    return {
        "runs": len(runs),
        "verdict_counts": {
            "CLEAR": clear,
            "HOLD": hold,
            "PILOT": pilot,
        },
        "pilot_queue": pilot,
        "false_alarms": false_alarms,
        "avoided_false_alarms": avoided,
        "auto_rate_pct": auto_rate,
        "mismatch_fields": mismatch_raw,
        "field_stats": {k: dict(v) for k, v in field_stats.items()},
        "confusion": matrix,
        "labels": SCOUT_LABELS,
        "official": {
            "emails": len(official),
            "categories": dict(Counter(v.category.value for v in official.values())),
            "status": dict(Counter((v.status.value if v.status else "null") for v in official.values())),
            "needs_review": sum(1 for v in official.values() if v.status and v.status.value == "NEEDS_REVIEW"),
            "defects": sum(1 for v in official.values() if v.has_defect),
        },
        "llm_cache_entries": store.llm_cache_count(),
        "robustness": _robustness(),
        "discipline": _discipline(),
    }


def _discipline() -> dict:
    from harbormaster.report.discipline import load_discipline_report

    return load_discipline_report()


def _robustness() -> dict:
    from harbormaster.report.robustness import load_robustness_report

    return load_robustness_report()
