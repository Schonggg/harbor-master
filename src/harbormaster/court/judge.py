from harbormaster.models import CourtDecision, VerdictState


def judge(mismatches: list[str]) -> CourtDecision:
    if not mismatches:
        return CourtDecision(verdict=VerdictState.MATCH, reason="No mismatches")
    return CourtDecision(verdict=VerdictState.UNCERTAIN, reason="Requires pilot review")
