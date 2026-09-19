from __future__ import annotations

from pathlib import Path

from harbormaster.ledger.store import LedgerStore
from harbormaster.report.robustness import load_robustness_report

ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_source_never_mentions_ground_truth():
    src = ROOT / "src" / "harbormaster"
    hits = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "ground_truth" in text and path.name != "robustness.py":
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_score_against_gt_is_only_in_the_harness():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "calibrate_seeds", ROOT / "scripts" / "calibrate_seeds.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    gt = {
        "e1": {
            "category": "BL_COMPARISON",
            "status": "OK",
            "review_reason": None,
            "has_defect": False,
            "defect_fields": [],
        }
    }
    pred = {
        "e1": {
            "category": "BL_COMPARISON",
            "status": "OK",
            "review_reason": None,
            "has_defect": False,
            "defect_fields": [],
        }
    }
    scored = mod.score_against_gt(pred, gt)
    assert scored["n"] == 1
    assert scored["exact"] == 1
    assert scored["score_pct"] == 100.0
    assert mod.find_generator() is None or mod.find_generator().name == "generate.py"


def test_metrics_exposes_robustness_talking_point():
    report = load_robustness_report()
    assert "generate.py" in report["talking_point"]
    assert "ground_truth.json" in report["talking_point"]


def test_get_run_by_ref_does_not_need_list_runs(tmp_path, monkeypatch):
    from harbormaster.config import clear_caches

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    store = LedgerStore()
    store.save_run("run-x", "case-x", "email_x", "PILOT", {"card": {"verdict": "PILOT"}})
    assert store.get_run_by_ref("case-x")["email_id"] == "email_x"
    assert store.get_run_by_ref("email_x")["run_id"] == "run-x"
    assert store.get_run_by_ref("missing") is None
