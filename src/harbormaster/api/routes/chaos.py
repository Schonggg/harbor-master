from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from harbormaster.graph.pipeline import run_from_request
from harbormaster.models import RunRequest
from harbormaster.reliability.chaos import CHAOS_TYPES

router = APIRouter()

# in-memory last chaos for dial demo
_LAST_CHAOS: dict = {}


class ChaosBody(BaseModel):
    email_id: str | None = None


@router.get("/chaos/types")
def chaos_types():
    return {"types": list(CHAOS_TYPES)}


@router.post("/chaos/{chaos_type}")
def trigger_chaos(chaos_type: str, body: ChaosBody | None = None):
    if chaos_type not in CHAOS_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown chaos type: {chaos_type}")
    req = RunRequest(
        email_id=(body.email_id if body else None),
        chaos=[chaos_type],
        degrade=chaos_type == "llm_timeout",
    )
    result = run_from_request(req)
    payload = result.model_dump(mode="json")
    _LAST_CHAOS[chaos_type] = payload
    return payload
