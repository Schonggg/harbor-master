from fastapi import APIRouter
router = APIRouter(prefix="/review", tags=["review"])

@router.get("/queue")
def queue() -> dict:
    return {"items": []}
