"""Local object store, hashed API keys, and ops endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from harbormaster.api.security import auth_required
from harbormaster.config import clear_caches
from harbormaster.keys import generate_api_key, hash_api_key, hashes_match, key_prefix
from harbormaster.ledger.store import LedgerStore
from harbormaster.models import is_demo_email_id
from harbormaster.storage.factory import reset_object_store
from harbormaster.storage.local import LocalObjectStore
from harbormaster.storage.s3 import canonical_uri
from tests.test_security import _request


def test_human_can_close_pilot_mail_as_clear_or_hold(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    store = LedgerStore()
    store.save_run(
        "run-pilot",
        "case-pilot",
        "demo_weight_hold",
        "PILOT",
        {"card": {"verdict": "PILOT", "subject": "weight", "email_id": "demo_weight_hold"}},
    )
    from harbormaster.api.routes.review import CaseVerdictBody, set_case_verdict

    out = set_case_verdict(CaseVerdictBody(case_id="case-pilot", verdict="CLEAR", reviewer="pilot"))
    assert out["verdict"] == "CLEAR"
    assert len(out.get("rules") or []) == 1
    assert out["rules"][0]["field"] == "case"
    assert out["rules"][0]["left_pattern"] == "demo_weight_hold"
    assert out.get("reply_draft")
    rows = store.list_runs()
    assert rows[0]["verdict"] == "CLEAR"
    assert rows[0]["payload"]["card"]["pilot_override"] is True
    assert rows[0]["payload"]["card"].get("reply_draft")
    set_case_verdict(CaseVerdictBody(case_id="demo_weight_hold", verdict="HOLD"))
    assert store.list_runs()[0]["verdict"] == "HOLD"


def test_closing_pilot_mail_teaches_remaining_si_bl_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    store = LedgerStore()
    pair = {
        "field": "shipper",
        "state": "UNCERTAIN",
        "left_value": "ACME PTE LTD",
        "right_value": "ACME Pte. Ltd.",
        "charge": {
            "left": {"raw_value": "ACME PTE LTD"},
            "right": {"raw_value": "ACME Pte. Ltd."},
        },
    }
    store.save_run(
        "run-teach",
        "case-teach",
        "email_teach",
        "PILOT",
        {"card": {"verdict": "PILOT", "field_verdicts": [pair]}},
    )
    store.save_run(
        "run-twin",
        "case-twin",
        "email_twin",
        "PILOT",
        {"card": {"verdict": "PILOT", "field_verdicts": [dict(pair)]}},
    )
    from harbormaster.api.routes.review import CaseVerdictBody, set_case_verdict

    out = set_case_verdict(CaseVerdictBody(case_id="case-teach", verdict="CLEAR", reviewer="pilot"))
    assert out["verdict"] == "CLEAR"
    fields = {r["field"] for r in out["rules"]}
    assert fields == {"shipper", "case"}
    assert any(r["field"] == "shipper" and r["decision"] == "accept_as_match" for r in out["rules"])
    rules = store.list_rules(active_only=True)
    assert {r.field for r in rules} == {"shipper", "case"}
    taught = store.get_run_by_ref("case-teach")
    assert taught["verdict"] == "CLEAR"
    twin = store.get_run_by_ref("case-twin")
    assert twin["payload"]["card"]["field_verdicts"][0]["state"] == "MATCH"
    again = set_case_verdict(CaseVerdictBody(case_id="case-teach", verdict="CLEAR", reviewer="pilot"))
    assert again["rules"] == []
    assert len(store.list_rules(active_only=True)) == 2


def test_three_pilot_clears_each_write_a_ledger_row(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    store = LedgerStore()
    from harbormaster.api.routes.review import CaseVerdictBody, set_case_verdict

    for n in ("email_a", "email_b", "email_c"):
        store.save_run(f"run-{n}", f"case-{n}", n, "PILOT", {"card": {"verdict": "PILOT", "email_id": n}})
        out = set_case_verdict(CaseVerdictBody(case_id=f"case-{n}", verdict="CLEAR", reviewer="pilot"))
        assert len(out["rules"]) == 1
        assert out["rules"][0]["field"] == "case"
    rules = store.list_rules(active_only=True)
    assert len(rules) == 3
    assert {r.left_pattern for r in rules} == {"email_a", "email_b", "email_c"}


def test_ledger_backfills_older_pilot_stamps_without_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    monkeypatch.delenv("HARBORMASTER_API_KEY", raising=False)
    clear_caches()
    store = LedgerStore()
    for n in ("email_old_1", "email_old_2", "email_old_3"):
        store.save_run(
            f"run-{n}",
            f"case-{n}",
            n,
            "CLEAR",
            {"card": {"verdict": "CLEAR", "email_id": n, "pilot_override": True, "pilot_override_by": "pilot"}},
        )
    assert store.list_rules() == []
    from harbormaster.api.main import app

    rows = TestClient(app).get("/api/ledger").json()
    assert len(rows) == 3
    assert {r["field"] for r in rows} == {"case"}
    assert {r["left_pattern"] for r in rows} == {"email_old_1", "email_old_2", "email_old_3"}
    again = TestClient(app).get("/api/ledger").json()
    assert len(again) == 3


def test_save_run_keeps_one_row_per_email(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    store = LedgerStore()
    store.save_run("run-a", "case-a", "email_001", "PILOT", {"n": 1})
    store.save_run("run-b", "case-b", "email_001", "CLEAR", {"n": 2})
    store.save_run("run-c", "case-c", "email_002", "HOLD", {"n": 3})
    rows = store.list_runs()
    assert {r["email_id"] for r in rows} == {"email_001", "email_002"}
    first = next(r for r in rows if r["email_id"] == "email_001")
    assert first["run_id"] == "run-b"
    assert first["verdict"] == "CLEAR"


def test_list_runs_hides_demo_when_official_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    store = LedgerStore()
    store.save_run("run-d", "case-d", "demo_si_vs_bl", "CLEAR", {})
    store.save_run("run-o", "case-o", "email_001", "HOLD", {})
    rows = store.list_runs()
    assert {r["email_id"] for r in rows} == {"email_001"}


def test_purge_demo_runs_drops_replay_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    store = LedgerStore()
    store.save_run("run-d", "case-d", "demo_weight_hold", "CLEAR", {})
    store.save_run("run-o", "case-o", "email_002", "PILOT", {})
    assert store.purge_demo_runs() >= 1
    assert {r["email_id"] for r in store.list_runs()} == {"email_002"}


def test_is_demo_email_id():
    assert is_demo_email_id("demo_si_vs_bl") is True
    assert is_demo_email_id("email_001") is False
    assert is_demo_email_id(None) is False


def test_s3_canonical_uri():
    assert canonical_uri("/bucket/backups/x.db") == "/bucket/backups/x.db"
    assert canonical_uri("bucket/a b") == "/bucket/a%20b"


def test_local_object_store_roundtrip(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    ref = store.put("exports/hello.json", b'{"ok":true}', "application/json")
    assert ref.backend == "local"
    assert store.get("exports/hello.json") == b'{"ok":true}'
    assert store.exists("exports/hello.json")
    health = store.health()
    assert health["ok"] is True


def test_key_hash_never_equals_plaintext():
    raw = generate_api_key()
    digest = hash_api_key(raw)
    assert raw.startswith("hm_")
    assert digest != raw
    assert hashes_match(raw, digest)
    assert not hashes_match(raw + "x", digest)
    assert "…" in key_prefix(raw)


def test_issue_key_and_match(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    reset_object_store()
    store = LedgerStore()
    raw = generate_api_key()
    issued = store.issue_api_key("ci", raw, key_prefix(raw), hash_api_key(raw))
    assert issued["key"] == raw
    listed = store.list_api_keys()
    assert listed[0]["prefix"] == key_prefix(raw)
    assert "key_hash" not in listed[0]
    assert store.match_api_key(raw)
    assert not store.match_api_key("nope")
    assert store.revoke_api_key(issued["key_id"])
    assert not store.match_api_key(raw)


def test_issued_key_gates_api(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    monkeypatch.delenv("HARBORMASTER_API_KEY", raising=False)
    clear_caches()
    reset_object_store()
    store = LedgerStore()
    raw = generate_api_key()
    store.issue_api_key("gate", raw, key_prefix(raw), hash_api_key(raw))
    try:
        auth_required(_request("/api/runs"))
        raise AssertionError("expected 401")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401
    auth_required(_request("/api/runs", {"x-api-key": raw}))
    auth_required(_request("/health"))


def test_ops_status_and_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    monkeypatch.delenv("S3_BUCKET", raising=False)
    clear_caches()
    reset_object_store()
    from harbormaster.api.main import app

    client = TestClient(app)
    status = client.get("/api/ops/status")
    assert status.status_code == 200
    body = status.json()
    assert body["storage"]["backend"] == "local"
    assert "compute" in body
    backup = client.post("/api/ops/backup")
    assert backup.status_code == 200
    payload = backup.json()
    assert payload["object"]["backend"] == "local"
    health = client.get("/health").json()
    assert "storage" in health
    assert "sk-" not in str(health).lower()
    assert health["keys"]["issued"] == 0
