"""Risk pricing engine."""

from __future__ import annotations

from harbormaster.config import get_risk_matrix
from harbormaster.models import CaseVerdict, CourtState, FieldVerdict, RiskAdvice, RiskLevel


class RiskEngine:
    def __init__(self) -> None:
        self.matrix = get_risk_matrix()

    def advise(self, field: str) -> RiskAdvice:
        r = self.matrix.for_field(field)
        return RiskAdvice(
            field=field,
            risk_level=RiskLevel(r.risk_level),
            exposure_usd=r.exposure_usd,
            advise=r.advise,
            weight=r.weight,
        )

    def enrich(self, verdicts: list[FieldVerdict]) -> list[FieldVerdict]:
        out: list[FieldVerdict] = []
        for fv in verdicts:
            advice = self.advise(fv.field)
            out.append(
                fv.model_copy(
                    update={
                        "risk_level": advice.risk_level,
                        "exposure_usd": advice.exposure_usd,
                        "advise": advice.advise,
                    }
                )
            )
        return out

    def total_exposure(self, verdicts: list[FieldVerdict]) -> float:
        return sum(
            fv.exposure_usd
            for fv in verdicts
            if fv.state in {CourtState.MISMATCH, CourtState.UNCERTAIN}
        )

    def rollup(self, verdicts: list[FieldVerdict], force_pilot: bool = False) -> CaseVerdict:
        if force_pilot:
            return CaseVerdict.PILOT
        if any(fv.state == CourtState.MISMATCH for fv in verdicts):
            return CaseVerdict.HOLD
        if any(fv.state == CourtState.UNCERTAIN for fv in verdicts):
            return CaseVerdict.PILOT
        return CaseVerdict.CLEAR
