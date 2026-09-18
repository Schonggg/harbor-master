from fastapi import APIRouter

from harbormaster.graph.pipeline import run_pipeline

router = APIRouter(prefix="", tags=["runs"])


@router.post("/run")
def run(email_id: str) -> dict:
    return run_pipeline(email_id)


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return {"run_id": run_id, "status": "done"}
