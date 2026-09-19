"""Keep unit tests on SQLite even if .env points at Postgres."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _sqlite_tests(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    from harbormaster.config import clear_caches

    clear_caches()
