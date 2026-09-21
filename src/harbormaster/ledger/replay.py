"""Replay historical cases after a new ledger rule lands."""

from __future__ import annotations

from harbormaster.ledger.store import LedgerStore, normalized_pair_key
from harbormaster.models import CaseVerdict, CourtState, PilotDecision


def _rollup(field_verdicts: list[dict]) -> str:
    states = [fv.get("state") for fv in field_verdicts]
    if CourtState.MISMATCH.value in states:
        return CaseVerdict.HOLD.value
    if CourtState.UNCERTAIN.value in states:
        return CaseVerdict.PILOT.value
    return CaseVerdict.CLEAR.value


def rule_id_from_rationale(rationale: str) -> str | None:
    text = str(rationale or "")
    for prefix in ("ledger replay:", "ledger:"):
        if text.startswith(prefix):
            rid = text[len(prefix) :].strip()
            return rid or None
    return None


def _cites_rule(rationale: str, rule_id: str) -> bool:
    return rule_id_from_rationale(rationale) == rule_id


class Replayer:
    def __init__(self, store: LedgerStore | None = None) -> None:
        self.store = store or LedgerStore()

    def replay(self, rule_id: str) -> dict:
        rules = {r.rule_id: r for r in self.store.list_rules(active_only=False)}
        rule = rules.get(rule_id)
        if not rule or not rule.active or rule.field == "case":
            return {"updated": 0, "rule_id": rule_id}

        updated = 0
        for run in self.store.list_runs():
            payload = run["payload"]
            card = payload.get("card") or {}
            field_verdicts = card.get("field_verdicts") or []
            changed = False
            for fv in field_verdicts:
                if fv.get("field") != rule.field:
                    continue
                charge = fv.get("charge") or {}
                left = (charge.get("left") or {}).get("raw_value", "")
                right = (charge.get("right") or {}).get("raw_value", "")
                if not str(left).strip() or not str(right).strip():
                    continue
                if normalized_pair_key(left, right) != rule.normalized_key:
                    continue
                if rule.decision == PilotDecision.ACCEPT_AS_MATCH:
                    fv["state"] = CourtState.MATCH.value
                    fv["rationale"] = f"ledger replay:{rule.rule_id}"
                    fv["winning_strategy"] = "ledger"
                    changed = True
                elif rule.decision == PilotDecision.CONFIRM_MISMATCH:
                    fv["state"] = CourtState.MISMATCH.value
                    fv["rationale"] = f"ledger replay:{rule.rule_id}"
                    changed = True
            if changed:
                # Human Pilot stamps are final. Pair replay may still paint fields, but must not
                # roll the case back to PILOT when UNCERTAIN fields remain.
                if not card.get("pilot_override"):
                    card["verdict"] = _rollup(field_verdicts)
                payload["card"] = card
                self.store.save_run(
                    run["run_id"], run["case_id"], run["email_id"], card["verdict"], payload
                )
                updated += 1
        return {"updated": updated, "rule_id": rule_id}

    def undo(self, rule_id: str) -> dict:
        """After revoke: peel this rule's paint off fields and re-open auto-closed mail."""
        if not rule_id:
            return {"updated": 0, "rule_id": rule_id}
        updated = 0
        for run in self.store.list_runs():
            payload = run["payload"]
            card = payload.get("card") or {}
            field_verdicts = card.get("field_verdicts") or []
            changed = False
            for fv in field_verdicts:
                if not _cites_rule(fv.get("rationale") or "", rule_id):
                    continue
                fv["state"] = CourtState.UNCERTAIN.value
                fv["rationale"] = "ledger revoke"
                if fv.get("winning_strategy") == "ledger":
                    fv["winning_strategy"] = None
                changed = True
            if not changed:
                continue
            # Human CLEAR/HOLD stamps stay put. Auto-closed mail re-opens to Pilot/Hold.
            if not card.get("pilot_override"):
                card["verdict"] = _rollup(field_verdicts)
            payload["card"] = card
            self.store.save_run(
                run["run_id"], run["case_id"], run["email_id"], card.get("verdict") or run["verdict"], payload
            )
            updated += 1
        return {"updated": updated, "rule_id": rule_id}
