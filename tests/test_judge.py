"""Three-state judge boundaries."""

from __future__ import annotations

from harbormaster.court.judge import Judge
from harbormaster.models import (
    Charge,
    CourtState,
    Evidence,
    EvidenceSource,
    ExtractedDocument,
    FieldValue,
)


def _fv(name: str, value: str, conf: float = 0.95) -> FieldValue:
    return FieldValue(
        name=name,
        raw_value=value,
        confidence=conf,
        evidence=Evidence(raw_text=value, source=EvidenceSource.TEXT),
    )


def test_match_via_strategy():
    left = ExtractedDocument(fields={"consignee": _fv("consignee", "ACME CO., LTD.")})
    right = ExtractedDocument(fields={"consignee": _fv("consignee", "ACME INC")})
    verdicts, _ = Judge().try_case(left, right, case_id="t1")
    assert verdicts[0].state == CourtState.MATCH
    assert verdicts[0].left_value == "ACME CO., LTD."
    assert verdicts[0].right_value == "ACME INC"


def test_raw_equality_keeps_both_writings():
    left = ExtractedDocument(fields={"shipper": _fv("shipper", "ACME TRADING")})
    right = ExtractedDocument(fields={"shipper": _fv("shipper", "ACME TRADING")})
    verdicts, _ = Judge().try_case(left, right, case_id="t-eq")
    assert verdicts[0].state == CourtState.MATCH
    assert verdicts[0].charge is None
    assert verdicts[0].left_value == "ACME TRADING"
    assert verdicts[0].right_value == "ACME TRADING"


def test_mismatch_when_confident_and_undefended():
    left = ExtractedDocument(fields={"consignee": _fv("consignee", "ALPHA CORP", 0.99)})
    right = ExtractedDocument(fields={"consignee": _fv("consignee", "BETA CORP", 0.99)})
    verdicts, _ = Judge().try_case(left, right, case_id="t2")
    assert verdicts[0].state == CourtState.MISMATCH


def test_uncertain_when_low_confidence():
    left = ExtractedDocument(fields={"consignee": _fv("consignee", "ALPHA", 0.4)})
    right = ExtractedDocument(fields={"consignee": _fv("consignee", "BETA", 0.4)})
    verdicts, _ = Judge().try_case(left, right, case_id="t3")
    assert verdicts[0].state == CourtState.UNCERTAIN


def test_two_value_resolves_grey_zone_to_mismatch():
    left = ExtractedDocument(fields={"consignee": _fv("consignee", "ALPHA CORP", 0.4)})
    right = ExtractedDocument(fields={"consignee": _fv("consignee", "BETA CORP", 0.4)})
    verdicts, _ = Judge(two_value=True).try_case(left, right, case_id="t3b")
    assert verdicts[0].state == CourtState.MISMATCH


def test_two_value_fuzzy_near_match_is_match():
    left = ExtractedDocument(fields={"shipper": _fv("shipper", "NORTHSTAR LOGISTICS")})
    right = ExtractedDocument(fields={"shipper": _fv("shipper", "NORTHSTAR LOGISTIC")})
    verdicts, _ = Judge(two_value=True).try_case(left, right, case_id="t3c")
    assert verdicts[0].state == CourtState.MATCH


def test_raw_equality_is_match():
    left = ExtractedDocument(fields={"consignee": _fv("consignee", "SAME CO")})
    right = ExtractedDocument(fields={"consignee": _fv("consignee", "SAME CO")})
    verdicts, _ = Judge().try_case(left, right, case_id="t4")
    assert verdicts[0].state == CourtState.MATCH
