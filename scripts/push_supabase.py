"""Upload official inbox + local ledger into Supabase Postgres.

The publishable API key cannot create tables or open a Postgres session.
Pass the Transaction pooler URI (port 6543) as DATABASE_URL.

  py -3 scripts/push_supabase.py --database-url "postgresql://postgres.PROJECT:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres"
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _sqlite_path() -> Path:
    raw = os.getenv("DB_PATH") or "./data/harbormaster.db"
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _bundle_inbox() -> Path | None:
    from harbormaster.config import bundle_dir

    bundle = bundle_dir()
    if bundle and (bundle / "inbox").is_dir():
        return bundle / "inbox"
    fallback = Path(r"D:\Downloads\sdoc-hackathon-bundle\inbox")
    if fallback.is_dir():
        return fallback
    return None


def _resolve_attachment(bundle_inbox: Path, path_str: str) -> Path:
    path = Path(path_str)
    if path.is_file():
        return path
    bundle = bundle_inbox.parent
    for root in (bundle, bundle_inbox, bundle_inbox.parent):
        candidate = root / path_str
        if candidate.is_file():
            return candidate
        named = root / "attachments" / Path(path_str).name
        if named.is_file():
            return named
    return path


def _kind_hint(name: str) -> str | None:
    from harbormaster.ingest.loader_adapter import _kind_hint as hint

    return hint(name)


def extract_text(path: Path) -> str:
    if not path.is_file():
        return ""
    from harbormaster.reader.detector import select_parser
    from harbormaster.reader.parsers.vision_parser import VisionParser

    parser = select_parser(path)
    if isinstance(parser, VisionParser):
        return ""
    try:
        return parser.parse(path) or ""
    except Exception:
        if path.suffix.lower() in {".txt", ".csv", ".md", ".json"}:
            return path.read_text(encoding="utf-8", errors="replace")
        return ""


def upload_inbox(store, inbox: Path) -> int:
    files = sorted(inbox.glob("email_*.json"))
    n = 0
    for json_path in files:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        email_id = str(data.get("email_id") or json_path.stem)
        raw_atts = data.get("attachments") or data.get("attachment_paths") or []
        if not isinstance(raw_atts, list):
            raw_atts = [raw_atts]
        attachments = []
        for item in raw_atts:
            if isinstance(item, str):
                rel, filename = item, Path(item).name
            elif isinstance(item, dict):
                rel = str(item.get("path") or item.get("filename") or item.get("name") or "")
                filename = str(item.get("filename") or item.get("name") or Path(rel).name)
            else:
                continue
            resolved = _resolve_attachment(inbox, rel)
            attachments.append(
                {
                    "filename": filename,
                    "original_path": rel,
                    "kind_hint": _kind_hint(filename),
                    "text": extract_text(resolved),
                }
            )
        store.save_inbox_email(
            email_id,
            subject=str(data.get("subject") or ""),
            from_addr=str(data.get("from") or data.get("from_addr") or ""),
            body_text=str(data.get("body") or data.get("body_text") or ""),
            payload=data,
            attachments=attachments,
            source="official",
        )
        n += 1
        if n % 50 == 0:
            print(f"  inbox {n}/{len(files)}")
    return n


def _sqlite_rows(db: Path, table: str, order: str = "") -> list[dict]:
    if not db.is_file():
        return []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if table not in names:
            return []
        suffix = f" ORDER BY {order}" if order else ""
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table}{suffix}").fetchall()]
    finally:
        conn.close()


def copy_ledger(store, db: Path) -> dict[str, int]:
    counts = {"case_runs": 0, "email_verdicts": 0, "ledger_rules": 0, "pilot_reviews": 0, "llm_cache": 0}
    seen_email: set[str] = set()
    for row in _sqlite_rows(db, "case_runs", "created_at DESC"):
        email_id = row["email_id"]
        if email_id in seen_email:
            continue
        seen_email.add(email_id)
        payload = json.loads(row["payload_json"] or "{}")
        store.save_run(
            row["run_id"],
            row["case_id"],
            email_id,
            row["verdict"],
            payload,
            created_at=row.get("created_at"),
        )
        counts["case_runs"] += 1
    from harbormaster.models import EmailVerdict, LedgerRule, PilotDecision, PilotReview

    for row in _sqlite_rows(db, "email_verdicts"):
        try:
            verdict = EmailVerdict(
                category=row["category"],
                status=row["status"] or None,
                review_reason=row["review_reason"] or None,
                has_defect=bool(row["has_defect"]),
                defect_fields=json.loads(row["defect_fields_json"] or "[]"),
            )
        except Exception:
            continue
        extra = json.loads(row["payload_json"] or "{}") if row.get("payload_json") else None
        store.save_verdict(row["email_id"], verdict, extra if isinstance(extra, dict) else None)
        counts["email_verdicts"] += 1
    from datetime import datetime

    for row in _sqlite_rows(db, "ledger_rules"):
        store.add_rule(
            LedgerRule(
                rule_id=row["rule_id"],
                field=row["field"],
                left_pattern=row["left_pattern"],
                right_pattern=row["right_pattern"],
                normalized_key=row["normalized_key"],
                decision=PilotDecision(row["decision"]),
                source_case_id=row["source_case_id"],
                active=bool(row["active"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                created_by=row["created_by"] or "pilot",
                revoked_at=datetime.fromisoformat(row["revoked_at"]) if row.get("revoked_at") else None,
                note=row["note"] or "",
            )
        )
        counts["ledger_rules"] += 1
    for row in _sqlite_rows(db, "pilot_reviews"):
        store.add_review(
            PilotReview(
                review_id=row["review_id"],
                case_id=row["case_id"],
                field=row["field"],
                decision=PilotDecision(row["decision"]),
                promote_to_ledger=bool(row["promote_to_ledger"]),
                reviewer=row["reviewer"],
                note=row["note"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        )
        counts["pilot_reviews"] += 1
    for row in _sqlite_rows(db, "llm_cache"):
        store.put_llm_cache(row["cache_key"], row["kind"], json.loads(row["payload_json"] or "{}"))
        counts["llm_cache"] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Push Harbormaster corpus + ledger to Supabase")
    parser.add_argument("--database-url", default="", help="Supabase Transaction pooler URI")
    parser.add_argument("--sqlite", default="", help="Local SQLite file to copy runs from")
    parser.add_argument("--skip-inbox", action="store_true")
    parser.add_argument("--skip-ledger", action="store_true")
    args = parser.parse_args()

    dsn = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
    if not (dsn.startswith("postgres://") or dsn.startswith("postgresql://")):
        print(
            "Need a Postgres connection string.\n"
            "Supabase Dashboard → Project Settings → Database → Connect → URI\n"
            "Choose Session or Transaction pooler (port 6543 for Vercel).\n"
            "Then:\n"
            "  py -3 scripts/push_supabase.py --database-url \"postgresql://postgres.xxxx:PASSWORD@...pooler.supabase.com:6543/postgres\"\n"
            "The publishable key alone cannot create tables or upload rows."
        )
        return 2

    os.environ["DATABASE_URL"] = dsn
    from harbormaster.config import clear_caches

    clear_caches()

    from harbormaster.ledger.store import LedgerStore

    store = LedgerStore()
    if store.backend != "postgres":
        print("LedgerStore did not switch to Postgres. Check DATABASE_URL.")
        return 2
    print(f"connected backend={store.backend}")

    if not args.skip_inbox:
        inbox = _bundle_inbox()
        if not inbox:
            print("official inbox not found (SDOC_BUNDLE_DIR / D:\\Downloads\\sdoc-hackathon-bundle)")
            return 2
        print(f"uploading inbox from {inbox}")
        n = upload_inbox(store, inbox)
        print(f"inbox_emails={n} hosted={store.inbox_count()}")

    if not args.skip_ledger:
        db = Path(args.sqlite) if args.sqlite else _sqlite_path()
        print(f"copying ledger from {db}")
        counts = copy_ledger(store, db)
        print("copied", counts)
        print(f"hosted runs={len(store.list_runs())}")

    print("done. Set the same DATABASE_URL on Vercel, then Redeploy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
