from fastapi import APIRouter
router = APIRouter(prefix="/ledger", tags=["ledger"])

@router.get("/rules")
def rules() -> dict:
    return {"rules": []}
