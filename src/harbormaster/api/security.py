"""API key gate. Open when no key is configured so the demo still one-clicks."""

from __future__ import annotations

import hmac
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from harbormaster.config import get_settings

PUBLIC_PREFIXES = (
    "/health",
    "/api/health",
    "/live",
    "/ready",
    "/version",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _configured_key() -> str:
    return get_settings().service_api_key


def extract_api_key(request: Request) -> str:
    header = request.headers.get("x-api-key") or ""
    if header.strip():
        return header.strip()
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.query_params.get("key") or "").strip()


def keys_match(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


_LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _hostname(value: str) -> str:
    host = (value or "").split("%")[0].strip().lower()
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    else:
        host = host.split(":")[0]
    return host.strip("[]")


def is_same_origin(request: Request) -> bool:
    host = request.headers.get("host") or ""
    for raw in (request.headers.get("origin"), request.headers.get("referer")):
        if not raw:
            continue
        parsed = urlparse(raw)
        candidate = parsed.netloc
        if candidate and host and candidate.lower() == host.lower():
            return True
    return False


def is_local_bridge(request: Request) -> bool:
    """Live Server / Vite on loopback talking to local FastAPI (dev only)."""
    if get_settings().harbormaster_env == "prod":
        return False
    if _hostname(request.headers.get("host") or "") not in _LOOPBACK:
        return False
    origin = request.headers.get("origin") or ""
    if not origin:
        return True
    return (urlparse(origin).hostname or "").lower() in _LOOPBACK


def _issued_keys_exist() -> bool:
    try:
        from harbormaster.ledger.store import LedgerStore

        return LedgerStore().active_api_key_count() > 0
    except Exception:
        return False


def _issued_key_ok(provided: str) -> bool:
    try:
        from harbormaster.ledger.store import LedgerStore

        return LedgerStore().match_api_key(provided)
    except Exception:
        return False


def auth_required(request: Request) -> None:
    expected = _configured_key()
    issued = _issued_keys_exist()
    if not expected and not issued:
        return
    path = request.url.path
    if path in {"/", "/favicon.ico"} or path.startswith("/static"):
        return
    if any(path == p or path.startswith(p.rstrip("/") + "/") for p in PUBLIC_PREFIXES):
        return
    if not path.startswith("/api"):
        return
    provided = extract_api_key(request)
    if expected and keys_match(provided, expected):
        return
    if provided and _issued_key_ok(provided):
        return
    if is_same_origin(request) or is_local_bridge(request):
        return
    raise HTTPException(
        status_code=401,
        detail="API key required. Send X-API-Key or Authorization: Bearer, or open the Bridge from the same origin.",
    )
