from pathlib import Path

from harbormaster.official.compare import values_match
from harbormaster.official.matrix import (
    EQUIVALENT,
    GOLD,
    NEAR_MISS,
    cells,
    false_alarm_pairs,
    run_matrix,
    would_false_alarm,
)
from harbormaster.reader.extractor import FieldExtractor


def test_every_equivalent_pair_is_not_a_false_alarm():
    for field, other in EQUIVALENT.items():
        assert values_match(field, GOLD[field], other), field
        assert would_false_alarm(field, GOLD[field], other) is False


def test_every_near_miss_still_fires():
    for field, other in NEAR_MISS.items():
        assert not values_match(field, GOLD[field], other), field


def test_notify_prefix_is_equivalent_writing():
    assert values_match("consignee", GOLD["consignee"], f"Notify: {GOLD['consignee']}")
    assert would_false_alarm("consignee", GOLD["consignee"], f"Notify: {GOLD['consignee']}") is False
    assert not values_match("consignee", GOLD["consignee"], f"Notify: {NEAR_MISS['consignee']}")


def test_port_unloc_parentheses_are_equivalent():
    assert values_match("port_of_loading", "SINGAPORE", "Singapore (SGSIN)")
    assert values_match("port_of_discharge", "PYEONGTAEK, SOUTH KOREA", "PYEONGTAEK, SOUTH KOREA (KRPTK)")
    assert not values_match("port_of_loading", "SINGAPORE", "ROTTERDAM (NLRTM)")


def test_extractor_strips_role_labels():
    text = (
        "Consignee: Notify: CLIFFORD PAPER INC\n"
        "Vessel Name: Name: VISION 202\n"
        "Voyage: V.002\n"
        "Port of Loading: SINGAPORE (SGSIN)\n"
    )
    doc = FieldExtractor(degrade=True, rules_only=True).extract_text(text)
    assert "NOTIFY" not in doc.fields["consignee"].raw_value.upper()
    assert "CLIFFORD" in doc.fields["consignee"].raw_value.upper()
    vessel = doc.fields["vessel_voyage"].raw_value.upper()
    assert not vessel.startswith("NAME:")
    assert "VISION 202" in vessel
    assert "V.002" in vessel


def test_false_alarm_report_is_zero():
    rows = false_alarm_pairs()
    assert rows
    assert all(r["equivalent_ok"] and r["near_miss_ok"] and not r["false_alarm"] for r in rows)


def test_compare_module_has_no_fuzzy_or_threshold():
    src = Path(__file__).resolve().parents[1] / "src" / "harbormaster" / "official" / "compare.py"
    body = "\n".join(
        line for line in src.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith(("#", '"""', "'''"))
    ).lower()
    for banned in ("difflib", "rapidfuzz", "levenshtein", "similarity", "ratio >"):
        assert banned not in body


def test_corrupt_pdf_does_not_crash(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a pdf")
    doc = FieldExtractor(degrade=True, rules_only=True).extract_path(path)
    assert isinstance(doc.text, str)


def test_format_matrix_ticks_every_cell(tmp_path):
    expected = len(cells())
    assert expected >= 7 * 4
    report = run_matrix(tmp_path)
    assert report["cells"] == expected
    failed = report["failed"]
    assert failed == [], [
        f"{r['field']}|{r['fmt']}|{r['label']!r}->{r['extracted']!r}" for r in failed[:12]
    ]
    assert report["passed"] == expected
    for fmt in report["formats"]:
        assert report["by_fmt"][fmt]["fail"] == 0
        assert report["by_fmt"][fmt]["ok"] > 0
