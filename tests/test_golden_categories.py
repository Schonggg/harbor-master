"""Golden emails covering the five official categories."""

from __future__ import annotations

from harbormaster.models import Category, EmailMessage
from harbormaster.scout.router import ScoutRouter


def _email(eid: str, subject: str, body: str, **meta) -> EmailMessage:
    return EmailMessage(email_id=eid, subject=subject, body_text=body, meta=meta)


def test_golden_categories_rules_only():
    router = ScoutRouter(degrade=True)
    cases = [
        (
            _email(
                "g_bl",
                "Please reconcile SI vs BL draft HM-1",
                "=== SHIPPING INSTRUCTION ===\nShipper: A\n=== BILL OF LADING DRAFT ===\nShipper: A\n",
            ),
            Category.BL_COMPARISON,
        ),
        (
            _email("g_si", "New shipping instruction needed for HM-2", "Please prepare a new shipping instruction."),
            Category.SI_REQUEST,
        ),
        (
            _email("g_inv", "Invoice query: freight charges", "The freight invoice shows THC charged twice."),
            Category.INVOICE_QUERY,
        ),
        (
            _email("g_spam", "Weekly marketing rates", "Click here to unsubscribe from future updates."),
            Category.SPAM,
        ),
        (
            _email("g_gen", "Booking confirmation HM-3", "Your space is confirmed for 2 x 40HC sailing 12 Oct."),
            Category.GENERAL,
        ),
    ]
    for email, expected in cases:
        got = router.route(email)
        assert got.category == expected, (email.email_id, got)
