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
