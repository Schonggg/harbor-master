"""FastAPI application + static Bridge UI."""

from __future__ import annotations

import logging
import sys
import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from harbormaster import __version__
from harbormaster.api.middleware import LocalNetworkMiddleware, RequestContextMiddleware
from harbormaster.api.routes import (
    autonomy,
    board,
    chaos,
    demo,
    ledger,
    metrics,
    ops,
    pilot,
    review,
    runs,
    submission,
)
from harbormaster.compute.worker import compute_status, start_backup_loop
from harbormaster.config import data_dir, get_settings, is_serverless, web_dir
from harbormaster.ingest.loader_adapter import LoaderAdapter
from harbormaster.ledger.db import public_db_label, redact_error
from harbormaster.ledger.store import LedgerStore
from harbormaster.llm.client import get_llm_client, llm_available
from harbormaster.logging import setup_logging
from harbormaster.storage.factory import get_object_store

load_dotenv()
setup_logging()

WEB_DIR = web_dir()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log = logging.getLogger("harbormaster")
    try:
        data_dir().mkdir(parents=True, exist_ok=True)
        LedgerStore()
        start_backup_loop()
        if not is_serverless() and "pytest" not in sys.modules:
            def _autoload() -> None:
                try:
                    from harbormaster.api.routes.demo import autoload_official

                    autoload_official()
                except Exception:
                    log.exception("official inbox autoload failed")

            threading.Thread(target=_autoload, name="hm-autoload", daemon=True).start()
    except Exception:
        log.exception("startup failed")
    yield


settings = get_settings()
app = FastAPI(
    title="Harbormaster",
    version=__version__,
    description="Shipping document verification: classify, extract, deterministic SI vs BL court.",
    lifespan=lifespan,
)
origins = settings.cors_origin_list
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
    allow_credentials=origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LocalNetworkMiddleware)
app.include_router(runs.router, prefix="/api", tags=["runs"])
app.include_router(board.router, prefix="/api", tags=["board"])
app.include_router(review.router, prefix="/api", tags=["review"])
app.include_router(pilot.router, prefix="/api", tags=["pilot"])
app.include_router(ledger.router, prefix="/api", tags=["ledger"])
app.include_router(chaos.router, prefix="/api", tags=["chaos"])
app.include_router(autonomy.router, prefix="/api", tags=["autonomy"])
app.include_router(metrics.router, prefix="/api", tags=["metrics"])
app.include_router(demo.router, prefix="/api", tags=["demo"])
app.include_router(submission.router, prefix="/api", tags=["submission"])
app.include_router(ops.router, prefix="/api", tags=["ops"])

NO_STORE = {"Cache-Control": "no-store, max-age=0"}


def _system_status(*, ping_llm: bool = False) -> dict:
    cfg = get_settings()
    inbox = LoaderAdapter().health()
    db_ok = True
    db_error = None
    cache_n = 0
    backend = "sqlite"
    try:
        store = LedgerStore()
        store.list_rules(active_only=False)
        cache_n = store.llm_cache_count()
        backend = store.backend
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        db_error = redact_error(str(exc))
    llm = get_llm_client()
    llm_info = {
        "configured": llm_available(),
        "base_url": cfg.openai_base_url,
        "model": llm.resolved_model or cfg.openai_model,
        "ok": None,
        "error": "",
        "cache_entries": cache_n,
    }
    if ping_llm and llm_available():
        ping = llm.ping()
        llm_info["ok"] = ping.get("ok")
        llm_info["model"] = ping.get("model") or llm_info["model"]
        llm_info["error"] = ping.get("error") or ""
    elif llm_available():
        llm_info["ok"] = True if llm.last_ok_at else None
        llm_info["error"] = llm.last_error
    storage = {"ok": True, "backend": "local", "error": ""}
    compute = {}
    issued_keys = 0
    try:
        storage = get_object_store().health()
        compute = compute_status()
        issued_keys = LedgerStore().active_api_key_count() if db_ok else 0
    except Exception as exc:  # noqa: BLE001
        storage = {"ok": False, "backend": "unknown", "error": str(exc)[:200]}
    status = "ok" if db_ok else "error"
    if db_ok and (storage.get("ok") is False or (llm_available() and llm_info.get("ok") is False)):
        status = "degraded"
    return {
        "status": status,
        "version": __version__,
        "env": cfg.harbormaster_env,
        "auth_required": bool(cfg.service_api_key) or issued_keys > 0,
        "inbox": inbox,
        "llm": llm_info,
        "db": {"ok": db_ok, "backend": backend, "path": public_db_label(), "error": db_error},
        "storage": storage,
        "compute": compute,
        "keys": {"bootstrap": bool(cfg.service_api_key), "issued": issued_keys},
    }


@app.get("/live")
def live():
    return {"status": "ok"}


@app.get("/health")
def health():
    return _system_status(ping_llm=False)


@app.get("/ready")
def ready():
    payload = _system_status(ping_llm=True)
    if payload["status"] == "error":
        return JSONResponse(payload, status_code=503)
    return payload


@app.get("/version")
def version():
    return {"version": __version__, "name": "harbormaster"}


@app.get("/api/health")
def api_health():
    return _system_status(ping_llm=False)


@app.get("/")
def index():
    index_path = WEB_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(404, "Bridge UI not bundled")
    return FileResponse(index_path, headers=NO_STORE)


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/{path:path}")
def web_asset(path: str):
    """Serve Bridge files at the site root so index.html relative URLs work."""
    if not WEB_DIR.exists():
        raise HTTPException(404)
    if path.startswith("api/"):
        raise HTTPException(404)
    candidate = (WEB_DIR / path).resolve()
    try:
        candidate.relative_to(WEB_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(404) from exc
    if candidate.is_file():
        return FileResponse(candidate, headers=NO_STORE)
    raise HTTPException(404)


def cli() -> None:
    import uvicorn

    uvicorn.run("harbormaster.api.main:app", host="0.0.0.0", port=8000, reload=True)
