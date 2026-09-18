from harbormaster.court.judge import judge


def run_pipeline(email_id: str) -> dict:
    decision = judge([])
    return {
        "email_id": email_id,
        "verdict": decision.verdict.value,
        "reason": decision.reason,
    }
