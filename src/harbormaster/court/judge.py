"""Judge — deterministic match/mismatch. LLM never sits here.

Bridge demo keeps a three-state verdict (MATCH / MISMATCH / UNCERTAIN).
Official graded output is two-value: grey-zone fuzzy scores resolve via a
tunable threshold to MATCH or MISMATCH. NEEDS_REVIEW is NOT used here.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from harbormaster.config import RiskMatrix, get_risk_matrix, runtime_thresholds
from harbormaster.court.defender import Defender
from harbormaster.court.prosecutor import Prosecutor
from harbormaster.court.strategies.locode_map import resolve_locode
from harbormaster.court.strategies.numeric_extract import extract_count
from harbormaster.court.strategies.suffix_strip import normalize_entity
from harbormaster.court.strategies.unit_convert import parse_weight_kg
from harbormaster.court.transcript import TranscriptWriter
from harbormaster.models import (
    Charge,
    CourtState,
    CourtTranscript,
    ExtractedDocument,
    FieldVerdict,
    Plea,
    RiskLevel,
)


_ENTITY_FIELDS = {"shipper", "consignee", "notify_party"}
_PORT_FIELDS = {"port_of_loading", "port_of_discharge"}
_WEIGHT_FIELDS = {"gross_weight", "gross_weight_kg"}
_COUNT_FIELDS = {"container_count"}


def _token_sort_ratio(left: str, right: str) -> float:
    a = " ".join(sorted(left.upper().split()))
    b = " ".join(sorted(right.upper().split()))
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class Judge:
    def __init__(
        self,
        prosecutor: Prosecutor | None = None,
        defender: Defender | None = None,
        risk: RiskMatrix | None = None,
        two_value: bool = False,
    ) -> None:
        self.prosecutor = prosecutor or Prosecutor()
        self.defender = defender or Defender()
        self.risk = risk or get_risk_matrix()
        self.two_value = two_value

    def adjudicate_charge(
        self,
        charge: Charge,
        transcript: CourtTranscript | None = None,
    ) -> FieldVerdict:
        tw = TranscriptWriter(transcript) if transcript else None
        if tw:
            tw.charge(charge)

        pleas = self.defender.defend(charge)
        if tw:
            for p in pleas:
                tw.plea(charge.field, p)

        risk = self.risk.for_field(charge.field)
        state, extra_plea = self._decide(charge, pleas)
        if extra_plea:
            pleas.append(extra_plea)
        winning = next((p.strategy for p in pleas if p.accepted), None)
        rationale = self._rationale(state, pleas, winning)

        fv = FieldVerdict(
            field=charge.field,
            state=state,
            charge=charge,
            pleas=pleas,
            winning_strategy=winning,
            rationale=rationale,
            risk_level=RiskLevel(risk.risk_level),
            exposure_usd=risk.exposure_usd,
            advise=risk.advise,
        )
        if tw:
            tw.verdict(fv)
        return fv

    def try_case(
        self,
        left_doc: ExtractedDocument,
        right_doc: ExtractedDocument,
        case_id: str,
        fields: list[str] | None = None,
    ) -> tuple[list[FieldVerdict], CourtTranscript]:
        transcript = CourtTranscript(case_id=case_id)
        charges = self.prosecutor.file_charges(left_doc, right_doc, fields=fields)
        verdicts: list[FieldVerdict] = []

        compared = fields or sorted(set(left_doc.fields) | set(right_doc.fields))
        charged_fields = {c.field for c in charges}
        for name in compared:
            if name in charged_fields:
                continue
            if name in left_doc.fields and name in right_doc.fields:
                risk = self.risk.for_field(name)
                fv = FieldVerdict(
                    field=name,
                    state=CourtState.MATCH,
                    rationale="raw equality",
                    risk_level=RiskLevel(risk.risk_level),
                    exposure_usd=risk.exposure_usd,
                    advise=risk.advise,
                )
                transcript.add("verdict", name, {"state": "MATCH", "rationale": "raw equality"})
                verdicts.append(fv)

        for charge in charges:
            verdicts.append(self.adjudicate_charge(charge, transcript=transcript))

        return verdicts, transcript

    def _decide(self, charge: Charge, pleas: list[Plea]) -> tuple[CourtState, Plea | None]:
        if any(p.accepted for p in pleas):
            return CourtState.MATCH, None

        thr = runtime_thresholds()
        if self.two_value:
            ratio, left_n, right_n = self._similarity(charge)
            accepted = ratio >= thr.fuzzy_match_threshold
            extra = Plea(
                strategy="fuzzy_threshold",
                accepted=accepted,
                argument=f"similarity {ratio:.3f} vs floor {thr.fuzzy_match_threshold:.3f}",
                transformed_left=left_n,
                transformed_right=right_n,
                confidence=ratio,
            )
            return (CourtState.MATCH if accepted else CourtState.MISMATCH), extra

        floor = thr.match_confidence_floor
        conf = min(charge.left.confidence, charge.right.confidence)
        if conf < thr.extract_min_confidence or conf < floor:
            return CourtState.UNCERTAIN, None
        return CourtState.MISMATCH, None

    def _similarity(self, charge: Charge) -> tuple[float, str, str]:
        field = charge.field
        left = charge.left.raw_value
        right = charge.right.raw_value
        if field in _WEIGHT_FIELDS or "weight" in field:
            lk = parse_weight_kg(left)
            rk = parse_weight_kg(right)
            if lk is None or rk is None:
                return 0.0, left, right
            return (1.0 if abs(lk - rk) <= 1.0 else 0.0), f"{lk:.4f}kg", f"{rk:.4f}kg"
        if field in _COUNT_FIELDS or "count" in field:
            ln = extract_count(left)
            rn = extract_count(right)
            if ln is None or rn is None:
                return 0.0, left, right
            return (1.0 if ln == rn else 0.0), str(ln), str(rn)
        if field in _PORT_FIELDS:
            ll = resolve_locode(left) or normalize_entity(left)
            rr = resolve_locode(right) or normalize_entity(right)
            if ll == rr and ll:
                return 1.0, ll, rr
            return _token_sort_ratio(ll, rr), ll, rr
        if field in _ENTITY_FIELDS:
            ll = normalize_entity(left)
            rr = normalize_entity(right)
            if ll == rr and ll:
                return 1.0, ll, rr
            return _token_sort_ratio(ll, rr), ll, rr
        ll = " ".join(left.upper().split())
        rr = " ".join(right.upper().split())
        if ll == rr:
            return 1.0, ll, rr
        return _token_sort_ratio(ll, rr), ll, rr

    def _rationale(self, state: CourtState, pleas: list[Plea], winning: str | None) -> str:
        if state == CourtState.MATCH and winning:
            return f"defended by {winning}"
        if state == CourtState.UNCERTAIN:
            return "confidence or evidence insufficient for HOLD"
        failed = ", ".join(p.strategy for p in pleas)
        return f"all strategies failed ({failed})"
