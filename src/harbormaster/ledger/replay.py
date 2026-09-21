"""Replay historical cases after a new ledger rule lands."""

from __future__ import annotations

from harbormaster.ledger.store import LedgerStore
from harbormaster.models import CaseVerdict, CourtState, PilotDecision


class Replayer:
    def __init__(self, store: LedgerStore | None = None) -> None:
        self.store = store or LedgerStore()

    def replay(self, rule_id: str) -> dict:
        rules = {r.rule_id: r for r in self.store.list_rules(active_only=False)}
        rule = rules.get(rule_id)
        if not rule:
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
                if rule.field == "case":
                    continue
                from harbormaster.ledger.store import normalized_pair_key

                if normalized_pair_key(left, right) != rule.normalized_key:
                    continue
                if rule.decision == PilotDecision.ACCEPT_AS_MATCH:
                    fv["state"] = CourtState.MATCH.value
                    fv["rationale"] = f"ledger replay:{rule.rule_id}"
                    changed = True
                elif rule.decision == PilotDecision.CONFIRM_MISMATCH:
                    fv["state"] = CourtState.MISMATCH.value
                    fv["rationale"] = f"ledger replay:{rule.rule_id}"
                    changed = True
            if changed:
                # Human Pilot stamps are final. Pair replay may still paint fields, but must not
                # roll the case back to PILOT when UNCERTAIN fields remain.
                if not card.get("pilot_override"):
                    states = [fv.get("state") for fv in field_verdicts]
                    if CourtState.MISMATCH.value in states:
                        card["verdict"] = CaseVerdict.HOLD.value
                    elif CourtState.UNCERTAIN.value in states:
                        card["verdict"] = CaseVerdict.PILOT.value
                    else:
                        card["verdict"] = CaseVerdict.CLEAR.value
                payload["card"] = card
                self.store.save_run(
                    run["run_id"], run["case_id"], run["email_id"], card["verdict"], payload
                )
                updated += 1
        return {"updated": updated, "rule_id": rule_id}
