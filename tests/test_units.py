from harbormaster.api.routes.runs import _board_payload
from harbormaster.court.strategies.unit_convert import parse_weight_kg


def test_mt_to_kg():
    assert parse_weight_kg("1 MT") == 1000.0


def test_lbs():
    kg = parse_weight_kg("2204.62 LBS")
    assert kg is not None
    assert abs(kg - 1000.0) < 1.0


def test_kgs_commas():
    assert parse_weight_kg("25,400 KGS") == 25400.0


def test_board_payload_keeps_defence_strategy():
    slim = _board_payload(
        {
            "card": {
                "subject": "SI vs BL",
                "verdict": "HOLD",
                "field_verdicts": [
                    {
                        "field": "port_of_loading",
                        "state": "MISMATCH",
                        "charge": {
                            "left": {"raw_value": "Shanghai", "confidence": 0.93},
                            "right": {"raw_value": "Ningbo", "confidence": 0.93},
                        },
                        "pleas": [
                            {
                                "strategy": "locode_map",
                                "accepted": False,
                                "argument": "Two different ports after LOCODE map",
                            }
                        ],
                        "risk_level": "high",
                        "advise": "HOLD — wrong load port",
                        "exposure_usd": 500000,
                    }
                ],
            }
        }
    )
    plea = slim["card"]["field_verdicts"][0]["pleas"][0]
    assert plea["strategy"] == "locode_map"
    assert plea["accepted"] is False
    assert "LOCODE" in plea["argument"]
    assert slim["card"]["lockable"] is True


def test_board_payload_lockable_needs_both_writings():
    missing_right = _board_payload(
        {
            "card": {
                "verdict": "PILOT",
                "field_verdicts": [
                    {
                        "field": "shipper",
                        "state": "UNCERTAIN",
                        "charge": {
                            "left": {"raw_value": "ACME", "confidence": 0.4},
                            "right": {"raw_value": "", "confidence": 0.4},
                        },
                    }
                ],
            }
        }
    )
    assert missing_right["card"]["lockable"] is False

    both = _board_payload(
        {
            "card": {
                "verdict": "PILOT",
                "field_verdicts": [
                    {
                        "field": "shipper",
                        "state": "UNCERTAIN",
                        "charge": {
                            "left": {"raw_value": "ACME LTD", "confidence": 0.4},
                            "right": {"raw_value": "ACME", "confidence": 0.4},
                        },
                    }
                ],
            }
        }
    )
    assert both["card"]["lockable"] is True

    smash = _board_payload(
        {
            "card": {
                "verdict": "PILOT",
                "failure_codes": ["ATTACHMENT_CORRUPT"],
                "field_verdicts": [],
            }
        }
    )
    assert smash["card"]["lockable"] is False
