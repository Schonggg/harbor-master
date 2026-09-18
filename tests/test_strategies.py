from harbormaster.court.strategies.suffix_strip import try_defend as suffix_strip


def test_suffix_strip_case_and_space_insensitive() -> None:
    assert suffix_strip("ACME", " acme ")
