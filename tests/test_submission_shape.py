from harbormaster.report.submission import build_submission


def test_submission_shape_has_required_keys() -> None:
    payload = build_submission("run-1", "PILOT", "Needs review")
    assert set(payload) == {"run_id", "verdict", "reason", "submission_version"}
