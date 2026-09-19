"""Official SDOC bundle: 520 emails + SI/BL attachments."""

from __future__ import annotations

from pathlib import Path

import pytest

from harbormaster.config import bundle_dir, clear_caches
from harbormaster.graph.pipeline import pick_seed_ids, run_from_request
from harbormaster.ingest.loader_adapter import LoaderAdapter
from harbormaster.models import Category, RunRequest
from harbormaster.reader.extractor import FieldExtractor
from harbormaster.reader.health_check import classify_doc_kind
from harbormaster.models import ExtractedDocument


pytestmark = pytest.mark.skipif(bundle_dir() is None, reason="official SDOC bundle not present")


def test_bundle_lists_520_emails():
    loader = LoaderAdapter()
    ids = loader.list_email_ids(source="official")
    assert len(ids) == 520
    assert "email_001" in ids
    health = loader.health()
    assert health["ok"] is True
    assert health["email_count"] == 520
    assert health["source"] == "bundle"


def test_email_001_attachments_resolve_and_extract():
    clear_caches()
    email = LoaderAdapter().load("email_001")
    assert email.subject
    assert len(email.attachments) == 2
    paths = [Path(p) for p in email.attachment_paths]
    assert all(p.is_file() for p in paths)
    extractor = FieldExtractor(rules_only=True, degrade=True)
    docs = [extractor.extract_path(p) for p in paths]
    kinds = {d.kind for d in docs}
    assert "si" in kinds and "bl" in kinds
    si = next(d for d in docs if d.kind == "si")
    bl = next(d for d in docs if d.kind == "bl")
    assert si.fields.get("shipper") and "APRIL" in si.fields["shipper"].raw_value.upper()
    assert si.fields.get("consignee") and bl.fields.get("consignee")
    assert si.fields.get("port_of_loading")
    assert si.fields.get("gross_weight_kg") or si.fields.get("gross_weight")


def test_filename_kind_si_bl():
    si = classify_doc_kind(ExtractedDocument(filename="email_001_SI.txt", text=""))
    bl = classify_doc_kind(ExtractedDocument(filename="email_001_BL.txt", text=""))
    assert si == "si"
    assert bl == "bl"


def test_official_email_runs_rules_court():
    result = run_from_request(
        RunRequest(email_id="email_001", rules_only=True, degrade=True, save_board=False)
    )
    assert result.official is not None
    assert result.official.category == Category.BL_COMPARISON
    assert result.official.status in {"OK", "MISMATCH", "NEEDS_REVIEW"}
    assert result.card.verdict.value in {"CLEAR", "HOLD", "PILOT"}


def test_inbox_catalog_has_subjects():
    items = LoaderAdapter().catalog(source="official")
    assert len(items) == 520
    first = next(i for i in items if i["email_id"] == "email_001")
    assert first["subject"]
    assert first["attachments"] >= 1


def test_seed_picks_demo_and_official():
    ids = pick_seed_ids()
    assert any(i.startswith("demo_") for i in ids)
    assert any(i.startswith("email_") for i in ids)
    assert "email_001" in ids or len([i for i in ids if i.startswith("email_")]) >= 8
