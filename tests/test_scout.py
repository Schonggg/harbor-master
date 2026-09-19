"""Scout SI_REQUEST vs BL_COMPARISON boundaries (no gold labels)."""

from __future__ import annotations

from harbormaster.config import runtime_thresholds
from harbormaster.models import AttachmentRef, Category, EmailMessage, ScoutResult
from harbormaster.scout.router import ScoutRouter
from harbormaster.scout.rules import official_rule_classify


def _email(eid: str, subject: str, body: str, attachments: list[str] | None = None) -> EmailMessage:
    atts = [
        AttachmentRef(filename=name, path=name)
        for name in (attachments or [])
    ]
    return EmailMessage(
        email_id=eid,
        subject=subject,
        body_text=body,
        attachments=atts,
        attachment_paths=[a.path for a in atts],
    )


def _route(email: EmailMessage) -> ScoutResult:
    return ScoutRouter(degrade=True).route(email)


def test_compare_verbs_are_bl_comparison():
    cases = [
        _email(
            "bl_compare",
            "Please reconcile SI vs BL draft HM-1",
            "Please compare the shipping instruction with the bill of lading.",
        ),
        _email(
            "bl_confirm_matches",
            "Docs for HM-2",
            "Can you confirm the BL matches the SI before we release?",
        ),
        _email(
            "bl_verify",
            "HM-3 draft",
            "Please verify the BL against the shipping instruction.",
        ),
        _email(
            "bl_check_against",
            "HM-4",
            "Please check the draft BL against the SI and revert.",
        ),
    ]
    for email in cases:
        got = official_rule_classify(email)
        assert got and got.category == Category.BL_COMPARISON, (email.email_id, got)
        assert _route(email).category == Category.BL_COMPARISON


def test_field_list_si_without_compare_verbs_is_si_request():
    email = _email(
        "si_fields",
        "Shipping instruction HM-12",
        "Please prepare a new shipping instruction.\nPOL: SINGAPORE\nPOD: ROTTERDAM\n"
        "Shipper: ACME\nConsignee: BETA",
    )
    got = official_rule_classify(email)
    assert got and got.category == Category.SI_REQUEST
    assert got.reason == "rule:si-request"
    assert got.confidence >= runtime_thresholds().scout_rule_confidence
    assert _route(email).category == Category.SI_REQUEST


def test_invoice_mentioning_si_and_bl_is_not_bl_or_si():
    email = _email(
        "inv_si_bl",
        "Freight invoice query HM-88",
        "Please advise the freight invoice for booking HM-88. The SI and BL were "
        "already filed last week; this is only a billing question about THC.",
    )
    got = official_rule_classify(email)
    assert got and got.category == Category.INVOICE_QUERY
    routed = _route(email)
    assert routed.category == Category.INVOICE_QUERY
    assert routed.category not in {Category.BL_COMPARISON, Category.SI_REQUEST}


def test_regression_find_si_plus_revert_draft_bl_is_si_request():
    """Synthetic of the 'Please find SI … revert with draft BL' swallow."""
    email = _email(
        "si_find_draft",
        "REQUEST SI _ HM-4412 _ ROTTERDAM",
        "Please find Shipping instruction for HM-4412.\n\n"
        "POL: SINGAPORE\nPOD: ROTTERDAM\n\n"
        "Shipper: ACME TRADING\nConsignee: BETA LOGISTICS\n\n"
        "Documents Required:\n1) 3 Original invoice\n2) 3 Packing list\n"
        "3) 3 Original BL + 3 N/N\nPlease revert with draft BL once available.",
    )
    got = official_rule_classify(email)
    assert got and got.category == Category.SI_REQUEST, got
    assert _route(email).category == Category.SI_REQUEST


def test_regression_si_needed_field_list_is_si_request():
    """Synthetic of RE_ SI NEEDED_ … field dump, no compare verb."""
    email = _email(
        "si_needed",
        "RE_ SI NEEDED_ HM-26773 _ MERSIN",
        "Please find Shipping instruction for HM-26773.\n"
        "POL: SHANGHAI\nPOD: MERSIN\nShipper: NORTH PAPER\nConsignee: UAB CARGO\n"
        "Please revert with draft BL once available.",
    )
    assert _route(email).category == Category.SI_REQUEST


def test_regression_house_bl_in_subject_is_still_si_request():
    """Synthetic of SI subject that also says HOUSE BL but body is a field list."""
    email = _email(
        "si_house_bl_subject",
        "SI - DIRECT - HM-45299 - BUSAN - HOUSE BL - 28-Jan-26",
        "Please find Shipping instruction for HM-45299.\n"
        "POL: NHAVA SHEVA\nPOD: BUSAN\nShipper: FAR EAST PAPER\n"
        "Consignee: EXPORT HOUSE\nPlease revert with draft BL once available.",
    )
    assert _route(email).category == Category.SI_REQUEST


def test_send_draft_bl_for_checking_is_bl_comparison():
    email = _email(
        "bl_send_check",
        "TO CONFIRM DOCS _ HM-03056",
        "Please assist to send the draft BL for HM-03056 for checking asap. Thank you.",
    )
    got = official_rule_classify(email)
    assert got and got.category == Category.BL_COMPARISON
    assert _route(email).category == Category.BL_COMPARISON


def test_attached_si_and_bl_with_check_stays_bl_comparison():
    email = _email(
        "pair_check",
        "TO CONFIRM DOCS _ HM-00133",
        "Attached are the SI and draft BL. Please check the details and confirm.",
        attachments=["email_pair_SI.txt", "email_pair_BL.txt"],
    )
    got = official_rule_classify(email)
    assert got and got.category == Category.BL_COMPARISON
    assert got.reason == "rule:si+bl attachments"
    assert _route(email).category == Category.BL_COMPARISON


def test_si_request_commits_above_rule_floor_without_llm():
    class _Poison:
        def classify(self, email: EmailMessage) -> ScoutResult:
            return ScoutResult(
                category=Category.BL_COMPARISON,
                confidence=0.99,
                reason="poison",
                route="llm",
            )

    email = _email(
        "si_floor",
        "New shipping instruction needed for HM-2",
        "Please prepare a new shipping instruction.",
    )
    routed = ScoutRouter(llm=_Poison(), degrade=False).route(email)
    assert routed.category == Category.SI_REQUEST
    assert routed.route == "rules"
    assert routed.confidence >= runtime_thresholds().scout_rule_confidence


def test_rpa_billing_process_is_general_not_invoice():
    email = _email(
        "rpa_billing",
        "_RPA_ India HSS SD Billing Process Completed - LE HAVRE",
        "This is an automated notification. The India HSS SD Billing Process "
        "has completed successfully. No action required. -- RPA Bot",
    )
    got = official_rule_classify(email)
    assert got and got.category == Category.GENERAL, got
    assert _route(email).category == Category.GENERAL


def test_advance_fee_phishing_with_invoice_subject_is_spam():
    email = _email(
        "phish_invoice",
        "Re: Invoice payment - kindly confirm your bank details",
        "Hello Dear, I am a bank officer with an urgent business proposal "
        "involving USD 4.5 million. Please reply with your bank details to proceed.",
    )
    got = official_rule_classify(email)
    assert got and got.category == Category.SPAM, got
    assert _route(email).category == Category.SPAM
