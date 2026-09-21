"""Chaos smash must stay inside the hosted 60s cap and must not rewrite official mail."""

from __future__ import annotations

from harbormaster.api.routes.chaos import ChaosBody, reset_chaos, trigger_chaos
from harbormaster.config import clear_caches
from harbormaster.ledger.store import LedgerStore


def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    return LedgerStore()


def test_empty_email_smash_is_pilot_without_inbox(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    out = trigger_chaos("empty_email", ChaosBody(email_id="email_001"))
    assert out["card"]["email_id"] == "chaos_empty_email"
    assert out["card"]["verdict"] == "PILOT"
    codes = out["card"]["failure_codes"]
    assert "EMPTY_EMAIL" in codes
    assert "CHAOS_INJECTED" in codes
    rows = store.list_runs()
    assert any(r["email_id"] == "chaos_empty_email" for r in rows)
    assert not any(r["email_id"] == "email_001" for r in rows)


def test_attachment_and_timeout_smashes_stay_on_chaos_ids(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    torn = trigger_chaos("attachment_corrupt", None)
    cut = trigger_chaos("llm_timeout", None)
    assert torn["card"]["verdict"] == "PILOT"
    assert "ATTACHMENT_CORRUPT" in torn["card"]["failure_codes"]
    assert cut["card"]["verdict"] == "PILOT"
    assert "LLM_TIMEOUT" in cut["card"]["failure_codes"]
    assert cut["card"]["degraded"] is True
    ids = {r["email_id"] for r in store.list_runs()}
    assert ids == {"chaos_attachment_corrupt", "chaos_llm_timeout"}


def test_chaos_reset_drops_smash_rows(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    store.save_run("run-keep", "case-keep", "email_001", "CLEAR", {"card": {"verdict": "CLEAR"}})
    trigger_chaos("ocr_garble", None)
    out = reset_chaos()
    assert out["dropped"] >= 1
    ids = {r["email_id"] for r in store.list_runs()}
    assert ids == {"email_001"}


def test_board_counts_ignore_chaos_smash_rows(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    store.save_run("run-a", "case-a", "email_001", "CLEAR", {"card": {"verdict": "CLEAR", "email_id": "email_001"}})
    store.save_run("run-b", "case-b", "email_002", "PILOT", {"card": {"verdict": "PILOT", "email_id": "email_002"}})
    trigger_chaos("empty_email", None)
    monkeypatch.delenv("HARBORMASTER_API_KEY", raising=False)
    from harbormaster.api.main import app
    from fastapi.testclient import TestClient

    body = TestClient(app).get("/api/board").json()
    assert body["counts"] == {"CLEAR": 1, "HOLD": 0, "PILOT": 1}
    assert any(r["email_id"] == "chaos_empty_email" for r in body["runs"])


def test_purge_email_prefix_refuses_official_shape(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    store.save_run("run-a", "case-a", "email_001", "CLEAR", {})
    assert store.purge_email_prefix("email_") == 0
    assert store.purge_email_prefix("") == 0
    assert {r["email_id"] for r in store.list_runs()} == {"email_001"}
