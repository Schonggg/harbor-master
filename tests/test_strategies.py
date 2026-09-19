"""Unit tests for the seven defense strategies."""

from __future__ import annotations

from harbormaster.court.strategies.label_synonym import LabelSynonymStrategy
from harbormaster.court.strategies.locode_map import LocodeMapStrategy
from harbormaster.court.strategies.numeric_extract import NumericExtractStrategy
from harbormaster.court.strategies.ocr_confusion import OcrConfusionStrategy
from harbormaster.court.strategies.ref_resolve import RefResolveStrategy
from harbormaster.court.strategies.suffix_strip import SuffixStripStrategy
from harbormaster.court.strategies.unit_convert import UnitConvertStrategy
from harbormaster.models import Charge, Evidence, EvidenceSource, FieldValue


def _charge(field: str, left: str, right: str, source: EvidenceSource = EvidenceSource.TEXT) -> Charge:
    ev = Evidence(raw_text=left, snippet=left, source=source)
    return Charge(
        field=field,
        left=FieldValue(name=field, raw_value=left, confidence=0.95, evidence=ev),
        right=FieldValue(
            name=field,
            raw_value=right,
            confidence=0.95,
            evidence=Evidence(raw_text=right, snippet=right, source=source),
        ),
    )


def test_suffix_strip():
    plea = SuffixStripStrategy().try_defend(
        _charge("consignee", "ACME SHIPPING CO., LTD.", "ACME SHIPPING INC")
    )
    assert plea.accepted


def test_suffix_strip_negative():
    plea = SuffixStripStrategy().try_defend(_charge("consignee", "ACME SHIPPING", "OMEGA SHIPPING"))
    assert not plea.accepted


def test_suffix_strip_edge_empty():
    plea = SuffixStripStrategy().try_defend(_charge("consignee", "CO., LTD.", "INC"))
    assert not plea.accepted


def test_locode_map():
    plea = LocodeMapStrategy().try_defend(
        _charge("port_of_loading", "Shanghai", "CNSHA")
    )
    assert plea.accepted


def test_locode_map_country_code():
    plea = LocodeMapStrategy().try_defend(
        _charge("port_of_loading", "Shanghai, China", "SHANGHAI, CN")
    )
    assert plea.accepted


def test_locode_map_negative():
    plea = LocodeMapStrategy().try_defend(
        _charge("port_of_loading", "Shanghai", "Los Angeles")
    )
    assert not plea.accepted


def test_unit_convert():
    plea = UnitConvertStrategy().try_defend(
        _charge("gross_weight_kg", "1 MT", "1000 KGS")
    )
    assert plea.accepted


def test_unit_convert_negative():
    plea = UnitConvertStrategy().try_defend(
        _charge("gross_weight_kg", "18400 KGS", "14800 KGS")
    )
    assert not plea.accepted


def test_unit_convert_edge_lbs_tolerance():
    plea = UnitConvertStrategy().try_defend(
        _charge("gross_weight_kg", "1000 KGS", "2204.62 LBS")
    )
    assert plea.accepted


def test_ref_resolve_both():
    plea = RefResolveStrategy().try_defend(
        _charge("notify_party", "SAME AS CONSIGNEE", "Same as Consignee")
    )
    assert plea.accepted


def test_ref_resolve_substitutes_consignee():
    charge = _charge("notify_party", "SAME AS CONSIGNEE", "ACME TRADING CO LTD")
    charge.note = "consignee_left=ACME TRADING CO LTD|consignee_right=ACME TRADING CO LTD"
    plea = RefResolveStrategy().try_defend(charge)
    assert plea.accepted


def test_ref_resolve_negative():
    charge = _charge("notify_party", "SAME AS CONSIGNEE", "OTHER PARTY LLC")
    charge.note = "consignee_left=ACME TRADING|consignee_right=ACME TRADING"
    plea = RefResolveStrategy().try_defend(charge)
    assert not plea.accepted


def test_numeric_extract():
    plea = NumericExtractStrategy().try_defend(
        _charge("container_count", "THREE (3) x 40HC", "3")
    )
    assert plea.accepted


def test_numeric_extract_negative():
    plea = NumericExtractStrategy().try_defend(
        _charge("container_count", "THREE (3) x 40HC", "4")
    )
    assert not plea.accepted


def test_numeric_extract_edge_word_only():
    plea = NumericExtractStrategy().try_defend(
        _charge("container_count", "TWO x 40HC", "2")
    )
    assert plea.accepted


def test_label_synonym_soft():
    plea = LabelSynonymStrategy().try_defend(_charge("port_of_loading", "POL", "Port of Loading"))
    assert plea.accepted


def test_label_synonym_negative():
    plea = LabelSynonymStrategy().try_defend(_charge("port_of_loading", "POL", "POD"))
    assert not plea.accepted


def test_ocr_confusion_guardrail_blocks_text():
    plea = OcrConfusionStrategy().try_defend(_charge("vessel_voyage", "EVER GIVEN", "EVER G1VEN"))
    assert not plea.accepted


def test_ocr_confusion_allows_ocr():
    plea = OcrConfusionStrategy().try_defend(
        _charge("vessel_voyage", "EVER GIVEN", "EVER G1VEN", source=EvidenceSource.OCR)
    )
    assert plea.accepted
