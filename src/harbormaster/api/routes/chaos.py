from fastapi import APIRouter
router = APIRouter(prefix="/chaos", tags=["chaos"])

@router.post("/{failure_type}")
def chaos(failure_type: str) -> dict:
    return {"failure_type": failure_type}
