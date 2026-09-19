from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from harbormaster.config import get_thresholds, runtime_thresholds, set_runtime_thresholds

router = APIRouter()

_HISTORY: list[dict] = []


class AutonomyBody(BaseModel):
    preset: str | None = None
    match_confidence_floor: float | None = Field(default=None, ge=0.5, le=1.0)
    uncertain_band: float | None = Field(default=None, ge=0.0, le=0.3)


@router.get("/autonomy")
def get_autonomy():
    t = runtime_thresholds()
    return {
        "thresholds": t.model_dump(),
        "history": _HISTORY[-50:],
    }


@router.post("/autonomy")
def set_autonomy(body: AutonomyBody):
    base = get_thresholds()
    if body.preset:
        t = base.apply_preset(body.preset)
    else:
        t = runtime_thresholds()
    updates = {}
    if body.match_confidence_floor is not None:
        updates["match_confidence_floor"] = body.match_confidence_floor
    if body.uncertain_band is not None:
        updates["uncertain_band"] = body.uncertain_band
    t = t.model_copy(update=updates)
    set_runtime_thresholds(t)
    point = {
        "match_confidence_floor": t.match_confidence_floor,
        "uncertain_band": t.uncertain_band,
        "preset": body.preset,
    }
    _HISTORY.append(point)
    return {"thresholds": t.model_dump(), "history": _HISTORY[-50:]}
