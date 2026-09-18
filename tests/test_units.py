from harbormaster.court.strategies.unit_convert import try_defend


def test_unit_convert_placeholder_is_false() -> None:
    assert try_defend("1 MT", "1000 KGS") is False
