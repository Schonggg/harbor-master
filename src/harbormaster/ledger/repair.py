"""One-shot repair for ledger bleed that wrongly auto-closed Pilot mail.

Older CLEAR stamps taught already-MATCH SI/BL pairs into the ledger and replayed
them across the corpus. This module revokes those mass-taught pair rules and peels
orphaned ledger paint so auto-closed mail re-opens to Pilot. Human CLEAR/HOLD
stamps (pilot_override) stay put. Deliberate Lock-in-Ledger rules stay active.
"""

from __future__ import annotations

from harbormaster.ledger.replay import _rollup, rule_id_from_rationale
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import CourtState

_REPAIR_MARKER = "ops:ledger_repair_v2"
_CASE_NOTES = frozenset({"case CLEAR", "case HOLD"})


def _is_mass_taught_pair(rule) -> bool:
    if getattr(rule, "field", None) == "case":
        return False
    return str(getattr(rule, "note", "") or "").strip() in _CASE_NOTES


def repair_ledger_closures(store: LedgerStore | None = None, *, force: bool = False) -> dict:
    """Idempotent. Safe to call from GET /runs and GET /ledger."""
    store = store or LedgerStore()
    rules = list(store.list_rules(active_only=False))
    bad = [r for r in rules if _is_mass_taught_pair(r)]
    bad_ids = {r.rule_id for r in bad}
    bad_active = [r for r in bad if r.active]

    prior = store.get_llm_cache(_REPAIR_MARKER)
    if prior and not force and not bad_active:
        base = prior if isinstance(prior, dict) else {}
        return {**base, "skipped": True, "marker": _REPAIR_MARKER}

    revoked = 0
    for rule in bad_active:
        store.revoke(rule.rule_id)
        revoked += 1

    active_ids = {
        r.rule_id
        for r in store.list_rules(active_only=True)
        if r.field != "case"
    }

    peeled_fields = 0
    repaired_runs = 0
    for run in store.list_runs():
        payload = dict(run.get("payload") or {})
        card = dict(payload.get("card") or {})
        # Human CLEAR/HOLD stamps are final — never peel or re-open them.
        if card.get("pilot_override"):
            continue
        field_verdicts = list(card.get("field_verdicts") or [])
        if not field_verdicts:
            continue
        changed = False
        for fv in field_verdicts:
            if not isinstance(fv, dict):
                continue
            rid = rule_id_from_rationale(fv.get("rationale") or "")
            if not rid:
                continue
            # Peel mass-taught paint and orphaned citations of revoked/missing rules.
            # Citations of still-active Lock-in-Ledger rules are left alone.
            if rid in bad_ids or rid not in active_ids:
                fv["state"] = CourtState.UNCERTAIN.value
                fv["rationale"] = "ledger repair"
                if fv.get("winning_strategy") == "ledger":
                    fv["winning_strategy"] = None
                peeled_fields += 1
                changed = True
        if not changed:
            continue
        card["verdict"] = _rollup(field_verdicts)
        card["field_verdicts"] = field_verdicts
        payload["card"] = card
        store.save_run(
            run["run_id"],
            run["case_id"],
            run["email_id"],
            card.get("verdict") or run["verdict"],
            payload,
        )
        repaired_runs += 1

    summary = {
        "skipped": False,
        "revoked_mass_taught": revoked,
        "bad_pair_rules": len(bad_ids),
        "repaired_runs": repaired_runs,
        "peeled_fields": peeled_fields,
        "marker": _REPAIR_MARKER,
    }
    store.put_llm_cache(_REPAIR_MARKER, "ops", summary)
    return summary
