def build_submission(run_id: str, verdict: str, reason: str) -> dict:
    return {
        "run_id": run_id,
        "verdict": verdict,
        "reason": reason,
        "submission_version": "1.0",
    }
