from fastapi import APIRouter
router = APIRouter(prefix="/autonomy", tags=["autonomy"])

@router.get("/threshold")
def threshold() -> dict:
    return {"classification_confidence": 0.8}
