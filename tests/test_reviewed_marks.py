"""Human-filed folder marks, independent of CaseCard / verdict."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from harbormaster.config import clear_caches
from harbormaster.ledger.store import LedgerStore, _as_dict


def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    monkeypatch.delenv("HARBORMASTER_API_KEY", raising=False)
    clear_caches()
    return LedgerStore()


def _seed(store: LedgerStore, email_id: str, verdict: str = "CLEAR") -> None:
    store.save_run(
        f"run-{email_id}",
        f"case-{email_id}",
        email_id,
        verdict,
        {"card": {"verdict": verdict, "subject": email_id, "email_id": email_id}},
    )


def test_mark_batch_lists_ids(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    store.mark_reviewed(["email_001", "email_002"], reviewed_by="desk")
    assert store.list_reviewed_email_ids() == {"email_001", "email_002"}


def test_remark_overwrites_timestamp(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    store.mark_reviewed(["email_001"], reviewed_by="a")
    with store._connect() as conn:
        first = _as_dict(
            conn.execute(
                "SELECT reviewed_at, reviewed_by FROM reviewed_marks WHERE email_id = ?",
                ("email_001",),
            ).fetchone()
        )
    time.sleep(0.02)
    store.mark_reviewed(["email_001"], reviewed_by="b")
    with store._connect() as conn:
        second = _as_dict(
            conn.execute(
                "SELECT reviewed_at, reviewed_by FROM reviewed_marks WHERE email_id = ?",
                ("email_001",),
            ).fetchone()
        )
    assert store.list_reviewed_email_ids() == {"email_001"}
    assert second["reviewed_by"] == "b"
    assert second["reviewed_at"] >= first["reviewed_at"]


def test_unmark_removes_id(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    store.mark_reviewed(["email_001", "email_002"])
    store.unmark_reviewed(["email_001"])
    assert store.list_reviewed_email_ids() == {"email_002"}


def test_board_cards_include_reviewed_flag(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    _seed(store, "email_001")
    _seed(store, "email_002")
    store.mark_reviewed(["email_002"])
    from harbormaster.api.main import app

    client = TestClient(app)
    body = client.get("/api/board").json()
    by_id = {c["email_id"]: c["reviewed"] for c in body["cards"]}
    assert by_id["email_001"] is False
    assert by_id["email_002"] is True
    assert all("reviewed" in c for c in body["cards"])


def test_post_board_reviewed_true(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from harbormaster.api.main import app

    client = TestClient(app)
    out = client.post("/api/board/reviewed", json={"email_ids": ["email_010"], "reviewed": True, "reviewed_by": "desk"})
    assert out.status_code == 200
    assert out.json() == {"ok": True, "count": 1, "reviewed": True}
    assert LedgerStore().list_reviewed_email_ids() == {"email_010"}


def test_post_board_reviewed_false(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    store.mark_reviewed(["email_010", "email_011"])
    from harbormaster.api.main import app

    client = TestClient(app)
    out = client.post("/api/board/reviewed", json={"email_ids": ["email_010"], "reviewed": False})
    assert out.status_code == 200
    assert out.json()["reviewed"] is False
    assert LedgerStore().list_reviewed_email_ids() == {"email_011"}


def test_runs_list_includes_reviewed_flag(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    _seed(store, "email_001")
    store.mark_reviewed(["email_001"])
    from harbormaster.api.main import app

    client = TestClient(app)
    rows = client.get("/api/runs").json()
    hit = next(r for r in rows if r["email_id"] == "email_001")
    assert hit["reviewed"] is True
    assert hit["payload"]["card"]["reviewed"] is True
    one = client.get(f"/api/runs/{hit['run_id']}").json()
    assert one["reviewed"] is True
    assert one["payload"]["card"]["reviewed"] is True


def test_clear_all_drops_reviewed_marks(tmp_path, monkeypatch):
    store = _iso(tmp_path, monkeypatch)
    _seed(store, "email_001")
    store.mark_reviewed(["email_001"])
    assert store.list_reviewed_email_ids()
    store.clear_all()
    assert store.list_reviewed_email_ids() == set()
    assert store.list_runs() == []
