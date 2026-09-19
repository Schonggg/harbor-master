from pathlib import Path

from harbormaster.config import clear_caches
from harbormaster.ingest.loader_adapter import LoaderAdapter
from harbormaster.ledger.store import LedgerStore


def test_inbox_roundtrip_and_cloud_load(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "harbormaster.db"))
    clear_caches()
    store = LedgerStore()
    store.save_inbox_email(
        "email_cloud_1",
        subject="SI vs BL",
        from_addr="desk@example.com",
        body_text="please check SI and draft BL",
        payload={"email_id": "email_cloud_1", "subject": "SI vs BL", "from": "desk@example.com"},
        attachments=[
            {"filename": "email_cloud_1_SI.txt", "kind_hint": "si", "text": "SHIPPER: ACME"},
            {"filename": "email_cloud_1_BL.txt", "kind_hint": "bl", "text": "SHIPPER: ACME"},
        ],
        source="official",
    )
    assert store.inbox_count() == 1
    assert store.list_inbox_ids() == ["email_cloud_1"]
    row = store.get_inbox_email("email_cloud_1")
    assert row is not None
    assert len(row["attachments"]) == 2

    loader = LoaderAdapter()
    email = loader.load("email_cloud_1", source="official")
    assert email.subject == "SI vs BL"
    assert len(email.attachments) == 2
    assert "SHIPPER" in Path(email.attachments[0].local_path).read_text(encoding="utf-8")
    catalog = loader.catalog(source="official")
    assert catalog[0]["source"] == "supabase"
    assert catalog[0]["attachments"] == 2
