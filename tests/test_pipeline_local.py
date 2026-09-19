"""End-to-end rules-only pass over local demo inbox."""

from __future__ import annotations

from harbormaster.graph.pipeline import run_corpus, run_from_request
from harbormaster.models import Category, RunRequest


def test_demo_si_vs_bl_rules_only():
    result = run_from_request(
        RunRequest(email_id="demo_si_vs_bl", rules_only=True, degrade=True, source="local")
    )
    assert result.official is not None
    assert result.official.category == Category.BL_COMPARISON
    rec = result.official.as_submission_dict()
    assert rec["status"] in {"OK", "MISMATCH", "NEEDS_REVIEW"}
    assert rec["decided_by"] in {"rule", "llm"}
    assert set(rec) == {"category", "status", "review_reason", "has_defect", "defect_fields", "decided_by"}


def test_local_corpus_covers_every_demo_id():
    out = run_corpus(source="local", rules_only=True, two_value=True, save_board=False)
    assert out["count"] >= 5
    assert not out["errors"]
    payload_path = out["path"]
    assert payload_path.endswith("submission.json")
    import json
    from pathlib import Path

    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    for rec in payload.values():
        assert rec["category"] in {
            "BL_COMPARISON",
            "SI_REQUEST",
            "INVOICE_QUERY",
            "GENERAL",
            "SPAM",
        }
        assert set(rec) == {"category", "status", "review_reason", "has_defect", "defect_fields", "decided_by"}
