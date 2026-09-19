"""Request ID, security headers, rate limit, auth, audit."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from harbormaster.api.security import auth_required
from harbormaster.config import get_settings


class LocalNetworkMiddleware(BaseHTTPMiddleware):
    """Chrome Local Network Access: Live Server :5500 → FastAPI :8000."""

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin") or "*"
        if request.method == "OPTIONS" and request.headers.get("access-control-request-private-network"):
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
                    "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers") or "*",
                    "Access-Control-Allow-Private-Network": "true",
                    "Access-Control-Max-Age": "600",
                },
            )
        response = await call_next(request)
        response.headers.setdefault("Access-Control-Allow-Private-Network", "true")
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        too_large = _body_too_large(request)
        if too_large is not None:
            too_large.headers["X-Request-ID"] = request_id
            return too_large
        try:
            auth_required(request)
        except Exception as exc:
            status = getattr(exc, "status_code", 401)
            detail = getattr(exc, "detail", str(exc))
            return JSONResponse(
                {"detail": detail},
                status_code=status,
                headers={"X-Request-ID": request_id},
            )
        limited = _rate_limit(request)
        if limited is not None:
            limited.headers["X-Request-ID"] = request_id
            return limited
        response = await call_next(request)
        _security_headers(response)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("Access-Control-Allow-Private-Network", "true")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith("/api"):
            _audit(request, response.status_code)
        return response


def _security_headers(response: Response) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault("X-DNS-Prefetch-Control", "off")
    response.headers.setdefault("Access-Control-Allow-Private-Network", "true")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; "
        "connect-src *; frame-ancestors 'none'",
    )


_HITS: dict[str, deque[float]] = defaultdict(deque)
_LOCK = Lock()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _body_too_large(request: Request) -> JSONResponse | None:
    settings = get_settings()
    raw = request.headers.get("content-length") or ""
    try:
        length = int(raw)
    except ValueError:
        return None
    if length > settings.max_body_bytes:
        return JSONResponse({"detail": "request body too large"}, status_code=413)
    return None


def _rate_limit(request: Request) -> JSONResponse | None:
    settings = get_settings()
    path = request.url.path
    if path in {"/health", "/live", "/ready", "/version"} or not path.startswith("/api"):
        return None
    from harbormaster.api.security import is_local_bridge, is_same_origin

    if settings.harbormaster_env != "prod" and (is_same_origin(request) or is_local_bridge(request)):
        return None
    heavy = path.endswith("/submit") or (
        path.rstrip("/").endswith("/run") and request.method == "POST"
    )
    limit = settings.rate_limit_heavy_per_min if heavy else settings.rate_limit_per_min
    key = f"{_client_ip(request)}:{'heavy' if heavy else 'std'}"
    now = time.time()
    with _LOCK:
        bucket = _HITS[key]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= limit:
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        bucket.append(now)
    return None


def _audit(request: Request, status: int) -> None:
    try:
        from harbormaster.ledger.store import LedgerStore

        LedgerStore().add_audit(
            method=request.method,
            path=request.url.path,
            status=status,
            ip=_client_ip(request),
            request_id=getattr(request.state, "request_id", ""),
        )
    except Exception:
        return
