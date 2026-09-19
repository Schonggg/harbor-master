"""AI Pilot closes UNCERTAIN / PILOT as CLEAR or HOLD."""

from __future__ import annotations

from harbormaster.graph.state import PipelineState
from harbormaster.models import (
    CaseCard,
    CaseVerdict,
    Category,
    Charge,
    CourtState,
    EmailMessage,
    Evidence,
    EvidenceSource,
    FieldValue,
    FieldVerdict,
    ScoutLabel,
    ScoutResult,
)
from harbormaster.pilot.ai_resolver import resolve_pilot


def _fv(name: str, value: str, conf: float = 0.4) -> FieldValue:
    return FieldValue(
        name=name,
        raw_value=value,
        confidence=conf,
        evidence=Evidence(raw_text=value, source=EvidenceSource.TEXT),
    )


class _FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload

    def cached_json(self, *_a, **_k):
        return self.payload


def _pilot_state() -> PipelineState:
    left = _fv("consignee", "ACME TRADING")
    right = _fv("consignee", "ACME TRADING CO")
    charge = Charge(field="consignee", left=left, right=right)
    fv = FieldVerdict(field="consignee", state=CourtState.UNCERTAIN, charge=charge, rationale="low confidence")
    email = EmailMessage(email_id="t_ai", subject="SI vs BL", body_text="Please check consignee.")
    card = CaseCard(
        email_id="t_ai",
        subject=email.subject,
        verdict=CaseVerdict.PILOT,
        field_verdicts=[fv],
        scout=ScoutResult(category=Category.BL_COMPARISON, label=ScoutLabel.BILL_OF_LADING, confidence=0.8, route="rules"),
    )
    return PipelineState(
        email=email,
        scout=card.scout,
        card=card,
        rules_only=False,
        degrade=False,
    )


def test_ai_pilot_accepts_match_to_clear(monkeypatch):
    monkeypatch.setattr("harbormaster.pilot.ai_resolver.llm_available", lambda: True)
    monkeypatch.setattr(
        "harbormaster.pilot.ai_resolver.get_llm_client",
        lambda: _FakeLLM(
            {
                "fields": [
                    {"field": "consignee", "decision": "accept_as_match", "reason": "same company", "confidence": 0.91}
                ],
                "case_verdict": "CLEAR",
                "reason": "writing noise only",
            }
        ),
    )
    state = _pilot_state()
    assert resolve_pilot(state) is True
    assert state.card.verdict == CaseVerdict.CLEAR
    assert state.card.ai_resolved is True
    assert state.card.field_verdicts[0].state == CourtState.MATCH
    assert state.interrupt is None


def test_ai_pilot_confirms_mismatch_to_hold(monkeypatch):
    monkeypatch.setattr("harbormaster.pilot.ai_resolver.llm_available", lambda: True)
    monkeypatch.setattr(
        "harbormaster.pilot.ai_resolver.get_llm_client",
        lambda: _FakeLLM(
            {
                "fields": [
                    {"field": "consignee", "decision": "confirm_mismatch", "reason": "different party", "confidence": 0.88}
                ],
                "case_verdict": "HOLD",
                "reason": "real discrepancy",
            }
        ),
    )
    state = _pilot_state()
    assert resolve_pilot(state) is True
    assert state.card.verdict == CaseVerdict.HOLD
    assert state.card.field_verdicts[0].state == CourtState.MISMATCH


def test_ai_pilot_skips_when_llm_off(monkeypatch):
    monkeypatch.setattr("harbormaster.pilot.ai_resolver.llm_available", lambda: False)
    state = _pilot_state()
    assert resolve_pilot(state) is False
    assert state.card.verdict == CaseVerdict.PILOT
