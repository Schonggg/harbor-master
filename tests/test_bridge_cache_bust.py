"""Header and board must load one store. Split ?v= recreates the empty-docket bug."""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def test_bridge_views_share_one_store_cache_bust():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")
    match = re.search(r"app\.js\?v=(\d+)", html)
    assert match, "index.html must cache-bust app.js"
    version = match.group(1)
    assert f"store.js?v={version}" in app
    for name in ("board", "court", "pilot", "ledger", "chaos", "metrics", "detail"):
        assert f"{name}.js?v={version}" in app, name
        text = (WEB / "views" / f"{name}.js").read_text(encoding="utf-8")
        assert f"store.js?v={version}" in text, name
        assert "ctx.store" in text, name
