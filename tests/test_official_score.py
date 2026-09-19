"""Official scoreboard persist — no ground truth, no invented F1."""

from __future__ import annotations

import json
from pathlib import Path

from harbormaster.report.official_score import (
    format_report,
    organizer_payload,
    persist_scoreboard,
)


def test_organizer_payload_strips_decided_by():
    raw = {
        "email_001": {
            "category": "GENERAL",
            "status": "OK",
            "review_reason": None,
            "has_defect": False,
            "defect_fields": [],
            "decided_by": "rule",
        }
    }
    out = organizer_payload(raw)
    assert set(out["email_001"]) == {
        "category",
        "status",
        "review_reason",
        "has_defect",
        "defect_fields",
    }
    assert "decided_by" not in out["email_001"]


def test_persist_appends_and_format_report(tmp_path: Path, monkeypatch):
    import harbormaster.report.official_score as mod

    monkeypatch.setattr(mod, "reports_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "history_dir", lambda: tmp_path / "official_scores")
    monkeypatch.setattr(mod, "latest_path", lambda: tmp_path / "official_score.json")
    empty = format_report()
    assert "No official score recorded yet" in empty
    persist_scoreboard(
        {
            "final_score": 0.81,
            "stage1": {"macro_f1": 0.9},
            "stage3": {"defect_f1": 0.7},
            "end_to_end": {"rate": 0.8},
            "reliability": {"unreadable": {"precision": 1.0}},
        },
        source="test",
    )
    latest = json.loads((tmp_path / "official_score.json").read_text(encoding="utf-8"))
    assert isinstance(latest, list)
    assert latest[-1]["scoreboard"]["final_score"] == 0.81
    text = format_report()
    assert "final_score: 0.81" in text
    assert "unreadable" in text
