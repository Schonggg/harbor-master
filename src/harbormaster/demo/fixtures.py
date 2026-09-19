"""Demo inbox fixtures for Bridge rehearsal."""

from __future__ import annotations

import json

from harbormaster.config import data_dir, db_path

DEMOS: dict[str, dict] = {
    "demo_si_vs_bl": {
        "subject": "SI vs BL — booking HM-2044 (alias storm)",
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
        "meta": {"demo": True, "tag": "shipping_instruction"},
    },
    "demo_hold_consignee": {
        "subject": "Urgent — BL draft for booking HM-2099",
        "from": "docs@freight.example",
        "to": ["desk@carrier.example"],
        "body": """BL for review.

=== SHIPPING INSTRUCTION ===
Consignee: NORTHSTAR LOGISTICS PTE LTD
Notify Party: NORTHSTAR LOGISTICS PTE LTD
Port of Loading: Singapore
Port of Discharge: Rotterdam
No. of Containers: 2
Gross Weight: 18400 KGS
Vessel / Voyage: MSC IRIS / 12W

=== BILL OF LADING DRAFT ===
Consignee: SOUTHPAC TRADING LLC
Notify Party: SOUTHPAC TRADING LLC
Port of Loading: SGSIN
Port of Discharge: NLRTM
Containers: 2
Gross Weight: 18400 KGS
Vessel / Voyage: MSC IRIS / 12W
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "bill_of_lading"},
    },
    "demo_pilot_ocr": {
        "subject": "Scanned BL — please validate ports",
        "from": "scan@ops.example",
        "to": ["desk@carrier.example"],
        "body": """OCR extract — low confidence.

=== SHIPPING INSTRUCTION ===
Consignee: HARBOR KEY CO LTD
Notify Party: SAME AS CONSIGNEE
Port of Loading: Ningbo
Port of Discharge: Long Beach
No. of Containers: 5
Gross Weight: 22046 LBS
Vessel / Voyage: COSCO SHIPPING / 88E

=== BILL OF LADING DRAFT ===
Consignee: HARBOR KEY CO LTD
Notify Party: SAME AS CONSIGNEE
Port of Loading: NINGB0
Port of Discharge: L0NG BEACH
Containers: 5
Gross Weight: 10 MT
Vessel / Voyage: COSCO SHIPPING / 88E
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "discrepancy_query", "force_low_conf": True},
    },
    "demo_clear_locode": {
        "subject": "Booking confirm HM-2110 — docs aligned",
        "from": "booking@line.example",
        "to": ["desk@carrier.example"],
        "body": """Aligned pair.

=== SHIPPING INSTRUCTION ===
Consignee: BLUEWAVE MARINE LIMITED
Notify Party: SAME AS CONSIGNEE
Port of Loading: Hong Kong
Port of Discharge: Hamburg
No. of Containers: ONE (1) x 20GP
Gross Weight: 8500 KGS
Vessel / Voyage: ONE HONGKONG / 03E

=== BILL OF LADING DRAFT ===
Consignee: BLUEWAVE MARINE LTD
Notify Party: SAME AS CONSIGNEE
Port of Loading: HKHKG
Port of Discharge: DEHAM
Containers: 1
Gross Weight: 8.5 MT
Vessel / Voyage: ONE HONGKONG / 03E
""",
        "attachments": [],
        "meta": {"demo": True, "tag": "booking_confirmation"},
    },
}


def reset_demo() -> dict:
    inbox = data_dir() / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (data_dir() / "attachments").mkdir(parents=True, exist_ok=True)

    # clear previous demo jsons
    for p in inbox.glob("demo_*.json"):
        p.unlink()

    written = []
    for email_id, payload in DEMOS.items():
        path = inbox / f"{email_id}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(email_id)

    from harbormaster.ledger.db import is_postgres

    if not is_postgres():
        db = db_path()
        if db.exists():
            db.unlink()
        return {"inbox": written, "db_cleared": str(db)}
    return {"inbox": written, "db_cleared": "postgres"}
