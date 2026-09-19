"""Auth, health, and backup smoke tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from harbormaster.api.security import auth_required, keys_match
from harbormaster.config import clear_caches


def _request(path: str, headers: dict | None = None, host: str = "testserver") -> Request:
    raw = [(b"host", host.encode())]
    for key, value in (headers or {}).items():
        raw.append((key.lower().encode(), value.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": raw,
        "client": ("127.0.0.1", 123),
        "server": (host, 80),
    }
    return Request(scope)


def test_keys_match_rejects_wrong_value():
    assert keys_match("abc", "abc")
    assert not keys_match("abc", "abd")
    assert not keys_match("", "abc")


def test_health_and_live_are_public():
    from harbormaster.api.main import app

    client = TestClient(app)
    assert client.get("/live").status_code == 200
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] in {"ok", "degraded", "error"}
    assert "llm" in body and "db" in body
    assert "storage" in body
    assert "sk-" not in str(body).lower()
    assert client.get("/api/health").status_code == 200
    assert client.get("/version").json()["name"] == "harbormaster"


def test_api_key_blocks_when_configured(monkeypatch):
    monkeypatch.setenv("HARBORMASTER_API_KEY", "secret-test-key")
    clear_caches()
    with pytest.raises(HTTPException) as blocked:
        auth_required(_request("/api/runs"))
    assert blocked.value.status_code == 401
    auth_required(_request("/api/runs", {"x-api-key": "secret-test-key"}))
    auth_required(_request("/health"))
    auth_required(_request("/api/runs", {"origin": "http://testserver"}, host="testserver"))
    monkeypatch.delenv("HARBORMASTER_API_KEY", raising=False)
    clear_caches()


def test_backup_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    from harbormaster.ledger.store import LedgerStore

    store = LedgerStore()
    dest = tmp_path / "backups" / "copy.db"
    store.backup(dest)
    assert dest.is_file()
    assert dest.stat().st_size > 0
