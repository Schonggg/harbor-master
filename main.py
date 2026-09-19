"""Vercel FastAPI entrypoint.

Vercel loads this file as `main:app`. We put `src/` on sys.path from several
possible roots (Drop, Git, Lambda task root) and fall back to an error app so
the deployment never dies as a blank FUNCTION_INVOCATION_FAILED page.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Visible constructor so Vercel's AST detector always sees a FastAPI `app`.
app = FastAPI(title="Harbormaster")


def _bootstrap_path() -> None:
    roots = [Path.cwd()]
    try:
        roots.insert(0, Path(__file__).resolve().parent)
    except NameError:
        pass
    for key in ("LAMBDA_TASK_ROOT", "VERCEL_FUNC_DIR"):
        raw = os.environ.get(key)
        if raw:
            roots.append(Path(raw))
    for root in roots:
        src = root / "src"
        if (src / "harbormaster").is_dir():
            text = str(src)
            if text not in sys.path:
                sys.path.insert(0, text)


_bootstrap_path()

try:
    from harbormaster.api.main import app as app  # noqa: F811
except Exception as exc:  # noqa: BLE001 — must still export FastAPI `app`
    _ERROR = f"{type(exc).__name__}: {exc}"
    _TRACE = traceback.format_exc()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def _boot_error(path: str = "") -> JSONResponse:
        return JSONResponse(
            {"ok": False, "error": _ERROR, "traceback": _TRACE, "path": path},
            status_code=500,
        )


__all__ = ["app"]
