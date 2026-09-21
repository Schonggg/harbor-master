from harbormaster.models import ReviewReason
from harbormaster.report.reply_draft import generate_outbox_from_run, generate_outbox_message


def test_hold_outbox_lists_si_bl_pair():
    text = generate_outbox_message(
        subject="Draft BL HM-9",
        category="BL_COMPARISON",
        status="MISMATCH",
        defect_fields=["shipper"],
        field_verdicts=[
            {
                "field": "shipper",
                "state": "MISMATCH",
                "charge": {
                    "left": {"raw_value": "ACME LTD"},
                    "right": {"raw_value": "ACME INC"},
                },
            }
        ],
        bridge_verdict="HOLD",
    )
    assert text
    assert "ACME LTD" in text
    assert "ACME INC" in text
    assert "Shipper" in text
    assert "never auto-sent" not in text.lower()


def test_clear_outbox_is_a_release_letter():
    text = generate_outbox_message(
        subject="SI vs BL",
        category="BL_COMPARISON",
        status="OK",
        bridge_verdict="CLEAR",
    )
    assert text
    assert "proceed" in text.lower()
    assert "Operator name" in text
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in text)


def test_pilot_outbox_asks_for_the_missing_file():
    text = generate_outbox_message(
        subject="Please check",
        category="BL_COMPARISON",
        status="NEEDS_REVIEW",
        review_reason=ReviewReason.MISSING_ATTACHMENT.value,
        bridge_verdict="PILOT",
    )
    assert text
    assert "re-attach" in text.lower()
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in text)


def test_outbox_from_run_does_not_change_defects():
    defects = ["consignee"]
    run = {
        "payload": {
            "card": {"subject": "amend BL", "field_verdicts": []},
            "official": {
                "category": "BL_COMPARISON",
                "status": "MISMATCH",
                "defect_fields": defects,
            },
        }
    }
    draft = generate_outbox_from_run(run, "HOLD")
    assert draft
    assert run["payload"]["official"]["defect_fields"] == ["consignee"]


def test_english_reply_draft_rewrites_legacy_chinese():
    from harbormaster.report.reply_draft import english_reply_draft

    payload = {
        "card": {
            "subject": "SI vs BL",
            "verdict": "CLEAR",
            "reply_draft": "关于本件：七项一致，可放行。\n\n[操作员姓名] / Harbormaster Desk",
            "field_verdicts": [],
        },
        "official": {"category": "BL_COMPARISON", "status": "OK"},
    }
    text = english_reply_draft(payload, "CLEAR")
    assert text
    assert "proceed" in text.lower()
    assert "Operator name" in text
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in text)
