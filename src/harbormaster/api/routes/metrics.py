from fastapi import APIRouter
router = APIRouter(prefix="/metrics", tags=["metrics"])

@router.get("/")
def metrics() -> dict:
    return {"false_alarms": 0}
