#!/usr/bin/env python3
"""Reset demo DB + seed inbox fixtures for Bridge demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harbormaster.config import data_dir  # noqa: E402

DEMOS = {
    "demo_si_vs_bl": {
        "subject": "SI vs BL check — booking HM-2044",
        "from": "ops@shipper.example",
        "to": ["desk@carrier.example"],
        "body": """Please reconcile SI and BL draft.

=== SHIPPING INSTRUCTION ===
Consignee: ACME TRADING CO., LTD.
Notify Party: SAME AS CONSIGNEE
Port of Loading: Shanghai
Port of Discharge: Los Angeles
No. of Containers: THREE (3) x 40HC
Gross Weight: 1 MT
Vessel / Voyage: EVER GIVEN / 001E

=== BILL OF LADING DRAFT ===
Consignee: ACME TRADING INC
Notify Party: SAME AS CONSIGNEE
Port of Loading: CNSHA
Port of Discharge: USLAX
Containers: 3
Gross Weight: 1000 KGS
Vessel / Voyage: EVER GIVEN / 001E
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "booking_confirmation"},
    },
    "demo_true_hold": {
        "subject": "Urgent: consignee mismatch on BL draft HM-2091",
        "from": "docs@forwarder.example",
        "to": ["desk@carrier.example"],
        "body": """Please check — shipper insists SI is correct.

=== SHIPPING INSTRUCTION ===
Consignee: NORTHSTAR LOGISTICS PTE LTD
Notify Party: SAME AS CONSIGNEE
Port of Loading: Singapore
Port of Discharge: Rotterdam
No. of Containers: 2
Gross Weight: 18400 KGS
Vessel / Voyage: MSC ISABELLA / 12W

=== BILL OF LADING DRAFT ===
Consignee: SOUTHPAC TRADING LLC
Notify Party: SAME AS CONSIGNEE
Port of Loading: Singapore
Port of Discharge: Rotterdam
Containers: 2
Gross Weight: 18400 KGS
Vessel / Voyage: MSC ISABELLA / 12W
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "bill_of_lading"},
    },
    "demo_pilot_gray": {
        "subject": "OCR scan — vessel name unclear HM-2102",
        "from": "scan@ops.example",
        "to": ["desk@carrier.example"],
        "body": """Scanned SI vs typed BL — please pilot.

=== SHIPPING INSTRUCTION ===
Consignee: HARBOR GATE CO LTD
Notify Party: Harbor Gate Co Ltd
Port of Loading: Busan
Port of Discharge: Long Beach
No. of Containers: FIVE (5) x 20GP
Gross Weight: 12.5 MT
Vessel / Voyage: ONE HANOI / 088E

=== BILL OF LADING DRAFT ===
Consignee: HARBOR GATE CO LTD
Notify Party: Harbor Gate Co Ltd
Port of Loading: Busan
Port of Discharge: Long Beach
Containers: 5
Gross Weight: 12500 KGS
Vessel / Voyage: 0NE HAN0I / 088E
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "discrepancy_query", "soft": True},
    },
    # Same OCR vessel pair across sibling bookings: one pilot decision on
    # HM-2102 replays onto these two, so the queue visibly collapses.
    "demo_pilot_gray_2": {
        "subject": "OCR scan — vessel name unclear HM-2107",
        "from": "scan@ops.example",
        "to": ["desk@carrier.example"],
        "body": """Scanned SI vs typed BL — same sailing as HM-2102.

=== SHIPPING INSTRUCTION ===
Consignee: MERIDIAN TEXTILES PTY LTD
Notify Party: SAME AS CONSIGNEE
Port of Loading: Busan
Port of Discharge: Long Beach
No. of Containers: TWO (2) x 40HC
Gross Weight: 19.2 MT
Vessel / Voyage: ONE HANOI / 088E

=== BILL OF LADING DRAFT ===
Consignee: MERIDIAN TEXTILES PTY LTD
Notify Party: SAME AS CONSIGNEE
Port of Loading: Busan
Port of Discharge: Long Beach
Containers: 2
Gross Weight: 19200 KGS
Vessel / Voyage: 0NE HAN0I / 088E
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "discrepancy_query", "soft": True},
    },
    "demo_pilot_gray_3": {
        "subject": "OCR scan — vessel name unclear HM-2111",
        "from": "scan@ops.example",
        "to": ["desk@carrier.example"],
        "body": """Scanned SI vs typed BL — same sailing as HM-2102.

=== SHIPPING INSTRUCTION ===
Consignee: KAPPA ELECTRONICS CO., LTD.
Notify Party: SAME AS CONSIGNEE
Port of Loading: Busan
Port of Discharge: Long Beach
No. of Containers: ONE (1) x 40HC
Gross Weight: 8.7 MT
Vessel / Voyage: ONE HANOI / 088E

=== BILL OF LADING DRAFT ===
Consignee: KAPPA ELECTRONICS CO LTD
Notify Party: SAME AS CONSIGNEE
Port of Loading: Busan
Port of Discharge: Long Beach
Containers: 1
Gross Weight: 8700 KGS
Vessel / Voyage: 0NE HAN0I / 088E
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "discrepancy_query", "soft": True},
    },
    # A different OCR pair: stays in the queue after the HM-2102 rule replays.
    "demo_pilot_algeciras": {
        "subject": "OCR scan — vessel unclear HM-2118",
        "from": "scan@ops.example",
        "to": ["desk@carrier.example"],
        "body": """Scanned SI vs typed BL — please pilot.

=== SHIPPING INSTRUCTION ===
Consignee: RIVERBEND FOODS INC
Notify Party: SAME AS CONSIGNEE
Port of Loading: Ningbo
Port of Discharge: Melbourne
No. of Containers: 4
Gross Weight: 61200 KGS
Vessel / Voyage: HMM ALGECIRAS / 0012W

=== BILL OF LADING DRAFT ===
Consignee: RIVERBEND FOODS INC
Notify Party: SAME AS CONSIGNEE
Port of Loading: Ningbo
Port of Discharge: Melbourne
Containers: 4
Gross Weight: 61200 KGS
Vessel / Voyage: HMM ALGEC1RAS / 0012W
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "discrepancy_query", "soft": True},
    },
    # The brief's own example: 3 vs 4 containers, weights agree → HOLD.
    "demo_container_hold": {
        "subject": "SI vs BL check — booking HM-2073",
        "from": "ops@shipper.example",
        "to": ["desk@carrier.example"],
        "body": """Please reconcile before release.

=== SHIPPING INSTRUCTION ===
Consignee: PACIFIC RIM IMPORTS LLC
Notify Party: SAME AS CONSIGNEE
Port of Loading: Shanghai
Port of Discharge: Los Angeles
No. of Containers: 3
Gross Weight: 22000 KGS
Vessel / Voyage: EVER GIVEN / 001E

=== BILL OF LADING DRAFT ===
Consignee: PACIFIC RIM IMPORTS LLC
Notify Party: SAME AS CONSIGNEE
Port of Loading: Shanghai
Port of Discharge: Los Angeles
Containers: 4
Gross Weight: 22000 KGS
Vessel / Voyage: EVER GIVEN / 001E
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "shipping_instruction"},
    },
    "demo_weight_hold": {
        "subject": "SI vs BL check — booking HM-2088",
        "from": "docs@forwarder.example",
        "to": ["desk@carrier.example"],
        "body": """Draft attached below, please verify.

=== SHIPPING INSTRUCTION ===
Consignee: AURORA MINERALS PTY LTD
Notify Party: SAME AS CONSIGNEE
Port of Loading: Brisbane
Port of Discharge: Singapore
No. of Containers: 2
Gross Weight: 18400 KGS
Vessel / Voyage: MSC ISABELLA / 12W

=== BILL OF LADING DRAFT ===
Consignee: AURORA MINERALS PTY LTD
Notify Party: SAME AS CONSIGNEE
Port of Loading: Brisbane
Port of Discharge: Singapore
Containers: 2
Gross Weight: 14800 KGS
Vessel / Voyage: MSC ISABELLA / 12W
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "shipping_instruction"},
    },
    "demo_locode_clear": {
        "subject": "SI vs BL check — booking HM-2126",
        "from": "ops@shipper.example",
        "to": ["desk@carrier.example"],
        "body": """Please reconcile SI and BL draft.

=== SHIPPING INSTRUCTION ===
Consignee: BALTIC FORWARDING GMBH
Notify Party: SAME AS CONSIGNEE
Port of Loading: Ningbo
Port of Discharge: Hamburg
No. of Containers: TWO (2) x 40HC
Gross Weight: 21.6 MT
Vessel / Voyage: CMA CGM MARCO POLO / 0FL2E

=== BILL OF LADING DRAFT ===
Consignee: BALTIC FORWARDING GMBH
Notify Party: SAME AS CONSIGNEE
Port of Loading: CNNGB
Port of Discharge: DEHAM
Containers: 2
Gross Weight: 21600 KGS
Vessel / Voyage: CMA CGM MARCO POLO / 0FL2E
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "shipping_instruction"},
    },
    # Classification-only traffic (no SI/BL to compare).
    "demo_invoice_query": {
        "subject": "Invoice query: freight charges on HM-2044",
        "from": "accounts@shipper.example",
        "to": ["desk@carrier.example"],
        "body": "Hi team, the freight invoice for HM-2044 shows THC charged twice. Could you confirm the correct amount before we pay?",
        "attachments": [],
        "meta": {"demo": True, "tag": "invoice_or_charges"},
    },
    "demo_booking_confirm": {
        "subject": "Booking confirmation HM-2130 Shanghai to Melbourne",
        "from": "bookings@carrier.example",
        "to": ["ops@shipper.example"],
        "body": "Your space is confirmed for 2 x 40HC sailing 12 Oct. Documentation cut-off is 10 Oct 17:00 local.",
        "attachments": [],
        "meta": {"demo": True, "tag": "booking_confirmation"},
    },
    "demo_amendment": {
        "subject": "Amendment request for HM-2091",
        "from": "docs@forwarder.example",
        "to": ["desk@carrier.example"],
        "body": "Please amend the party to be notified on HM-2091 to NORTHSTAR LOGISTICS PTE LTD, attention Ms. Lim. Nothing else changes.",
        "attachments": [],
        "meta": {"demo": True, "tag": "amendment_request"},
    },
    "demo_new_si_request": {
        "subject": "New shipping instruction needed for HM-2150",
        "from": "ops@shipper.example",
        "to": ["desk@carrier.example"],
        "body": "Please prepare a new shipping instruction for HM-2150: 2 x 20GP, ceramic tiles, Shenzhen to Jebel Ali. Draft to follow tomorrow.",
        "attachments": [],
        "meta": {"demo": True, "tag": "shipping_instruction"},
    },
    "demo_spam": {
        "subject": "Weekly marketing rates: Asia to Europe",
        "from": "promo@ratesblast.example",
        "to": ["desk@carrier.example"],
        "body": "Special marketing rates this week on all Asia to Europe lanes! Click here to unsubscribe from future updates.",
        "attachments": [],
        "meta": {"demo": True, "tag": "operational_noise"},
    },
}


def reset_demo() -> dict:
    inbox = data_dir() / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (data_dir() / "attachments").mkdir(parents=True, exist_ok=True)

    # wipe inbox json demos + db
    for p in inbox.glob("demo_*.json"):
        p.unlink()

    written = []
    for email_id, payload in DEMOS.items():
        path = inbox / f"{email_id}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(email_id)

    from harbormaster.ledger.store import LedgerStore

    store = LedgerStore()
    if store.backend == "postgres":
        return {"written": written, "db_cleared": False, "reason": "postgres ledger preserved"}
    store.clear_all()

    return {"written": written, "db_cleared": store.backend}


def main() -> None:
    result = reset_demo()
    print(f"demo reset: {result}")


if __name__ == "__main__":
    main()
