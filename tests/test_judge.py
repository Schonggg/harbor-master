from harbormaster.court.judge import judge
from harbormaster.models import VerdictState


def test_judge_no_mismatches_is_match() -> None:
    assert judge([]).verdict is VerdictState.MATCH
