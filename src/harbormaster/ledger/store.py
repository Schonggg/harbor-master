"""Ledger store — SQLite locally, Postgres (Supabase) when DATABASE_URL is postgresql://."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from harbormaster.config import db_path
from harbormaster.ledger.db import PgConn, connect_postgres, postgres_dsn
from harbormaster.models import (
    EmailVerdict,
    LedgerRule,
    PilotDecision,
    PilotReview,
    is_demo_email_id,
)

_PG_SCHEMA_READY = False


def _payload_from_row(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _run_from_row(row: Any) -> dict:
    return {
        "run_id": row["run_id"],
        "case_id": row["case_id"],
        "email_id": row["email_id"],
        "verdict": row["verdict"],
        "payload": _payload_from_row(row["payload_json"]),
        "created_at": row["created_at"],
    }


def _as_dict(row: Any) -> dict:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        ts = value
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T", 1)
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


class LedgerStore:
    def __init__(self, path: Path | None = None) -> None:
        if path is not None and str(path) == "<postgres>":
            path = None
        self.dsn = None if path is not None else postgres_dsn()
        self.path = path or (Path("<postgres>") if self.dsn else db_path())
        if not self.dsn:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._init_schema()
            except OSError:
                fallback = Path("/tmp/harbormaster/harbormaster.db")
                fallback.parent.mkdir(parents=True, exist_ok=True)
                self.path = fallback
                self._init_schema()
        else:
            self._init_schema()

    @property
    def backend(self) -> str:
        return "postgres" if self.dsn else "sqlite"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection | PgConn]:
        if self.dsn:
            with connect_postgres(self.dsn) as conn:
                yield conn
            return
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=8000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _schema_path(self) -> Path:
        name = "schema.pg.sql" if self.dsn else "schema.sql"
        path = Path(__file__).parent / name
        if path.is_file():
            return path
        return Path.cwd() / "src" / "harbormaster" / "ledger" / name

    def _upsert(self, conn: Any, table: str, pk: str, columns: list[str], values: tuple) -> None:
        cols = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        if self.dsn:
            non_pk = [c for c in columns if c != pk]
            sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk)
            sql = (
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) "
                f"ON CONFLICT ({pk}) DO UPDATE SET {sets}"
            )
        else:
            sql = f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"
        conn.execute(sql, values)

    def clear_all(self) -> None:
        """Truncate board tables. Hosted inbox emails stay — they are the corpus."""
        with self._connect() as conn:
            conn.execute("DELETE FROM case_runs")
            conn.execute("DELETE FROM pilot_reviews")
            conn.execute("DELETE FROM ledger_rules")
            conn.execute("DELETE FROM email_verdicts")
            conn.execute("DELETE FROM pipeline_jobs")
            conn.execute("DELETE FROM stored_objects")
            conn.execute("DELETE FROM reviewed_marks")

    def _init_schema(self) -> None:
        global _PG_SCHEMA_READY
        if self.dsn and _PG_SCHEMA_READY:
            return
        schema = self._schema_path().read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema)
        if self.dsn:
            _PG_SCHEMA_READY = True

    def mark_reviewed(self, email_ids: list[str], reviewed_by: str = "") -> None:
        """Batch-file emails as human-reviewed. Re-marking the same id refreshes the stamp."""
        now = datetime.now(timezone.utc).isoformat()
        who = str(reviewed_by or "")
        with self._connect() as conn:
            for eid in email_ids:
                token = str(eid or "").strip()
                if not token:
                    continue
                self._upsert(
                    conn,
                    "reviewed_marks",
                    "email_id",
                    ["email_id", "reviewed_by", "reviewed_at"],
                    (token, who, now),
                )

    def unmark_reviewed(self, email_ids: list[str]) -> None:
        """Undo a filed mark so the card returns to the open docket."""
        with self._connect() as conn:
            for eid in email_ids:
                token = str(eid or "").strip()
                if not token:
                    continue
                conn.execute("DELETE FROM reviewed_marks WHERE email_id = ?", (token,))

    def list_reviewed_email_ids(self) -> set[str]:
        """email_ids currently in the filed folder. Survives re-runs; not part of CaseCard."""
        with self._connect() as conn:
            rows = conn.execute("SELECT email_id FROM reviewed_marks").fetchall()
        out: set[str] = set()
        for row in rows:
            eid = str(_as_dict(row).get("email_id") or "").strip()
            if eid:
                out.add(eid)
        return out

    def add_rule(self, rule: LedgerRule) -> None:
        with self._connect() as conn:
            self._upsert(
                conn,
                "ledger_rules",
                "rule_id",
                [
                    "rule_id",
                    "field",
                    "left_pattern",
                    "right_pattern",
                    "normalized_key",
                    "decision",
                    "source_case_id",
                    "active",
                    "created_at",
                    "created_by",
                    "revoked_at",
                    "note",
                ],
                (
                    rule.rule_id,
                    rule.field,
                    rule.left_pattern,
                    rule.right_pattern,
                    rule.normalized_key,
                    rule.decision.value,
                    rule.source_case_id,
                    1 if rule.active else 0,
                    rule.created_at.isoformat(),
                    rule.created_by,
                    rule.revoked_at.isoformat() if rule.revoked_at else None,
                    rule.note,
                ),
            )

    def list_rules(self, active_only: bool = True) -> list[LedgerRule]:
        q = "SELECT * FROM ledger_rules"
        if active_only:
            q += " WHERE active = 1"
        q += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(q).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def revoke(self, rule_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE ledger_rules SET active = 0, revoked_at = ? WHERE rule_id = ?",
                (datetime.now(timezone.utc).isoformat(), rule_id),
            )

    def add_review(self, review: PilotReview) -> None:
        with self._connect() as conn:
            self._upsert(
                conn,
                "pilot_reviews",
                "review_id",
                [
                    "review_id",
                    "case_id",
                    "field",
                    "decision",
                    "promote_to_ledger",
                    "reviewer",
                    "note",
                    "created_at",
                ],
                (
                    review.review_id,
                    review.case_id,
                    review.field,
                    review.decision.value,
                    1 if review.promote_to_ledger else 0,
                    review.reviewer,
                    review.note,
                    review.created_at.isoformat(),
                ),
            )

    def save_run(
        self,
        run_id: str,
        case_id: str,
        email_id: str,
        verdict: str,
        payload: dict,
        created_at: str | None = None,
    ) -> None:
        if self.dsn and is_demo_email_id(email_id):
            return
        stamp = created_at or datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM case_runs WHERE email_id = ? AND run_id != ?", (email_id, run_id))
            self._upsert(
                conn,
                "case_runs",
                "run_id",
                ["run_id", "case_id", "email_id", "verdict", "payload_json", "created_at"],
                (
                    run_id,
                    case_id,
                    email_id,
                    verdict,
                    json.dumps(payload),
                    stamp,
                ),
            )

    def purge_demo_runs(self) -> int:
        """Throw away the 14-email replay so the board is only the official inbox."""
        n = 0
        with self._connect() as conn:
            for sql in (
                "DELETE FROM case_runs WHERE email_id LIKE ?",
                "DELETE FROM email_verdicts WHERE email_id LIKE ?",
            ):
                cur = conn.execute(sql, ("demo_%",))
                n += int(getattr(cur, "rowcount", 0) or 0)
        return n

    def purge_email_prefix(self, prefix: str) -> int:
        """Drop smash / fixture rows by email_id prefix. Official SDOC ids are never this shape."""
        token = str(prefix or "").strip()
        if not token or token in {"%", "_", "email_"}:
            return 0
        like = f"{token}%"
        n = 0
        with self._connect() as conn:
            for sql in (
                "DELETE FROM case_runs WHERE email_id LIKE ?",
                "DELETE FROM email_verdicts WHERE email_id LIKE ?",
            ):
                cur = conn.execute(sql, (like,))
                n += int(getattr(cur, "rowcount", 0) or 0)
        return n

    def list_runs(self) -> list[dict]:
        with self._connect() as conn:
            sql = "SELECT run_id, case_id, email_id, verdict, payload_json, created_at FROM case_runs"
            params: tuple = ()
            if self.dsn:
                sql += " WHERE email_id NOT LIKE ?"
                params = ("demo_%",)
            sql += " ORDER BY created_at DESC"
            rows = conn.execute(sql, params).fetchall()
        out: list[dict] = []
        seen: set[str] = set()
        for r in rows:
            email_id = r["email_id"]
            if email_id in seen:
                continue
            seen.add(email_id)
            out.append(_run_from_row(r))
        if any(not is_demo_email_id(r["email_id"]) for r in out):
            out = [r for r in out if not is_demo_email_id(r["email_id"])]
        return out

    def list_human_closed_runs(self) -> list[dict]:
        """Unique-email runs a Pilot human closed as CLEAR or HOLD."""
        with self._connect() as conn:
            sql = """
                SELECT run_id, case_id, email_id, verdict, payload_json, created_at
                FROM case_runs
                WHERE verdict IN ('CLEAR', 'HOLD')
                  AND (payload_json LIKE ? OR payload_json LIKE ?)
            """
            params: tuple = ('%"pilot_override": true%', '%"pilot_override":true%')
            if self.dsn:
                sql += " AND email_id NOT LIKE ?"
                params = params + ("demo_%",)
            sql += " ORDER BY created_at DESC"
            rows = conn.execute(sql, params).fetchall()
        out: list[dict] = []
        seen: set[str] = set()
        for r in rows:
            email_id = r["email_id"]
            if email_id in seen or is_demo_email_id(email_id):
                continue
            seen.add(email_id)
            run = _run_from_row(r)
            card = (run.get("payload") or {}).get("card") or {}
            if not card.get("pilot_override"):
                continue
            out.append(run)
        return out

    def get_run_by_ref(self, ref: str) -> dict | None:
        """Lookup by run_id, case_id, or email_id without scanning every payload."""
        if not ref:
            return None
        hit = self.get_run(ref)
        if hit:
            return hit
        with self._connect() as conn:
            r = conn.execute(
                """
                SELECT run_id, case_id, email_id, verdict, payload_json, created_at
                FROM case_runs
                WHERE run_id = ? OR case_id = ? OR email_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (ref, ref, ref),
            ).fetchone()
        if not r:
            return None
        return _run_from_row(r)

    def list_run_email_ids(self) -> set[str]:
        with self._connect() as conn:
            if self.dsn:
                rows = conn.execute(
                    "SELECT email_id FROM case_runs WHERE email_id NOT LIKE ?",
                    ("demo_%",),
                ).fetchall()
            else:
                rows = conn.execute("SELECT email_id FROM case_runs").fetchall()
        return {
            str(r["email_id"])
            for r in rows
            if r["email_id"] and not is_demo_email_id(r["email_id"])
        }

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT run_id, case_id, email_id, verdict, payload_json, created_at FROM case_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if not r:
            return None
        return _run_from_row(r)

    def find_matching_rule(self, field: str, left: str, right: str) -> LedgerRule | None:
        key = normalized_pair_key(left, right)
        for rule in self.list_rules(active_only=True):
            if rule.field == field and rule.normalized_key == key:
                return rule
        return None

    def get_llm_cache(self, cache_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM llm_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["payload_json"])

    def put_llm_cache(self, cache_key: str, kind: str, payload: dict) -> None:
        with self._connect() as conn:
            self._upsert(
                conn,
                "llm_cache",
                "cache_key",
                ["cache_key", "kind", "payload_json", "created_at"],
                (
                    cache_key,
                    kind,
                    json.dumps(payload),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def clear_llm_cache(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM llm_cache")

    def save_verdict(self, email_id: str, verdict: EmailVerdict, payload: dict | None = None) -> None:
        if self.dsn and is_demo_email_id(email_id):
            return
        with self._connect() as conn:
            self._upsert(
                conn,
                "email_verdicts",
                "email_id",
                [
                    "email_id",
                    "category",
                    "status",
                    "review_reason",
                    "has_defect",
                    "defect_fields_json",
                    "payload_json",
                    "created_at",
                ],
                (
                    email_id,
                    verdict.category.value,
                    verdict.status.value if verdict.status else None,
                    verdict.review_reason.value if verdict.review_reason else None,
                    1 if verdict.has_defect else 0,
                    json.dumps(verdict.defect_fields),
                    json.dumps(payload or verdict.as_submission_dict()),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_verdict(self, email_id: str) -> EmailVerdict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM email_verdicts WHERE email_id = ?",
                (email_id,),
            ).fetchone()
        if not row:
            return None
        return _row_to_verdict(row)

    def list_verdicts(self) -> dict[str, EmailVerdict]:
        with self._connect() as conn:
            if self.dsn:
                rows = conn.execute(
                    "SELECT * FROM email_verdicts WHERE email_id NOT LIKE ?",
                    ("demo_%",),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM email_verdicts").fetchall()
        return {r["email_id"]: _row_to_verdict(r) for r in rows}

    def save_job(
        self,
        job_id: str,
        status: str,
        total: int,
        processed: int,
        error: str | None = None,
        payload: dict | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM pipeline_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            created = existing["created_at"] if existing else now
            self._upsert(
                conn,
                "pipeline_jobs",
                "job_id",
                ["job_id", "status", "total", "processed", "error", "payload_json", "created_at", "updated_at"],
                (
                    job_id,
                    status,
                    total,
                    processed,
                    error,
                    json.dumps(payload or {}),
                    created,
                    now,
                ),
            )

    def get_job(self, job_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM pipeline_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        return {
            "job_id": row["job_id"],
            "status": row["status"],
            "total": row["total"],
            "processed": row["processed"],
            "error": row["error"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def latest_job(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pipeline_jobs ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        job = self.get_job(row["job_id"])
        if not job:
            return None
        if job.get("status") in {"running", "queued"}:
            ts = _parse_ts(job.get("updated_at")) or _parse_ts(job.get("created_at"))
            stale = ts is None or datetime.now(timezone.utc) - ts > timedelta(minutes=10)
            if stale:
                self.save_job(
                    job["job_id"],
                    "error",
                    int(job.get("total") or 0),
                    int(job.get("processed") or 0),
                    error="stale job",
                    payload=job.get("payload") or {},
                )
                job = {**job, "status": "error", "error": "stale job"}
        return job

    def add_audit(self, method: str, path: str, status: int, ip: str = "", request_id: str = "") -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (method, path, status, ip, request_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (method, path, status, ip, request_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.execute("DELETE FROM audit_log WHERE created_at < ?", (cutoff,))

    def llm_cache_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM llm_cache").fetchone()
        return int(row["n"] if row else 0)

    def issue_api_key(self, name: str, raw: str, prefix: str, key_hash: str) -> dict:
        from uuid import uuid4

        key_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_keys (key_id, name, prefix, key_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key_id, name.strip() or "integration", prefix, key_hash, now),
            )
        return {
            "key_id": key_id,
            "name": name.strip() or "integration",
            "prefix": prefix,
            "created_at": now,
            "key": raw,
        }

    def list_api_keys(self, include_revoked: bool = False) -> list[dict]:
        q = "SELECT key_id, name, prefix, created_at, last_used_at, revoked_at FROM api_keys"
        if not include_revoked:
            q += " WHERE revoked_at IS NULL"
        q += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(q).fetchall()
        return [_as_dict(r) for r in rows]

    def revoke_api_key(self, key_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE key_id = ? AND revoked_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), key_id),
            )
            return cur.rowcount > 0

    def match_api_key(self, provided: str) -> bool:
        from harbormaster.keys import hash_api_key, hashes_match

        if not provided:
            return False
        digest = hash_api_key(provided)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key_id, key_hash FROM api_keys WHERE revoked_at IS NULL AND key_hash = ?",
                (digest,),
            ).fetchone()
            if not row or not hashes_match(provided, row["key_hash"]):
                return False
            conn.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
                (datetime.now(timezone.utc).isoformat(), row["key_id"]),
            )
        return True

    def active_api_key_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM api_keys WHERE revoked_at IS NULL"
            ).fetchone()
        return int(row["n"] if row else 0)

    def record_object(self, ref) -> None:
        with self._connect() as conn:
            self._upsert(
                conn,
                "stored_objects",
                "object_key",
                ["object_key", "backend", "bytes", "content_type", "uri", "created_at"],
                (
                    ref.key,
                    ref.backend,
                    int(ref.bytes),
                    ref.content_type,
                    ref.uri,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def list_objects(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT object_key, backend, bytes, content_type, uri, created_at
                FROM stored_objects ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_as_dict(r) for r in rows]

    def object_stats(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(bytes), 0) AS bytes FROM stored_objects"
            ).fetchone()
        return {"count": int(row["n"] if row else 0), "bytes": int(row["bytes"] if row else 0)}

    def save_inbox_email(
        self,
        email_id: str,
        *,
        subject: str = "",
        from_addr: str = "",
        body_text: str = "",
        payload: dict | None = None,
        attachments: list[dict] | None = None,
        source: str = "official",
    ) -> None:
        atts = attachments or []
        with self._connect() as conn:
            self._upsert(
                conn,
                "inbox_emails",
                "email_id",
                [
                    "email_id",
                    "subject",
                    "from_addr",
                    "body_text",
                    "payload_json",
                    "attachments_json",
                    "attachment_count",
                    "source",
                    "created_at",
                ],
                (
                    email_id,
                    subject,
                    from_addr,
                    body_text,
                    json.dumps(payload or {}),
                    json.dumps(atts),
                    len(atts),
                    source,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def list_inbox_ids(self, source: str | None = None) -> list[str]:
        q = "SELECT email_id FROM inbox_emails"
        params: tuple = ()
        if source:
            q += " WHERE source = ?"
            params = (source,)
        q += " ORDER BY email_id"
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [r["email_id"] for r in rows]

    def inbox_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM inbox_emails").fetchone()
        return int(row["n"] if row else 0)

    def get_inbox_email(self, email_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM inbox_emails WHERE email_id = ?",
                (email_id,),
            ).fetchone()
        if not row:
            return None
        data = _as_dict(row)
        payload = json.loads(data.get("payload_json") or "{}")
        attachments = json.loads(data.get("attachments_json") or "[]")
        return {
            "email_id": data["email_id"],
            "subject": data.get("subject") or "",
            "from_addr": data.get("from_addr") or "",
            "body_text": data.get("body_text") or "",
            "payload": payload if isinstance(payload, dict) else {},
            "attachments": attachments if isinstance(attachments, list) else [],
            "attachment_count": int(data.get("attachment_count") or 0),
            "source": data.get("source") or "official",
        }

    def backup(self, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.dsn:
            snapshot = {
                "backend": "postgres",
                "runs": self.list_runs(),
                "inbox_ids": self.list_inbox_ids(),
                "rules": [r.model_dump(mode="json") for r in self.list_rules(active_only=False)],
            }
            dest.write_text(json.dumps(snapshot), encoding="utf-8")
            return dest
        import shutil

        with self._connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(self.path, dest)
        return dest

    @staticmethod
    def _row_to_rule(r: Any) -> LedgerRule:
        return LedgerRule(
            rule_id=r["rule_id"],
            field=r["field"],
            left_pattern=r["left_pattern"],
            right_pattern=r["right_pattern"],
            normalized_key=r["normalized_key"],
            decision=PilotDecision(r["decision"]),
            source_case_id=r["source_case_id"],
            active=bool(r["active"]),
            created_at=datetime.fromisoformat(r["created_at"]),
            created_by=r["created_by"],
            revoked_at=datetime.fromisoformat(r["revoked_at"]) if r["revoked_at"] else None,
            note=r["note"] or "",
        )


def _row_to_verdict(r: Any) -> EmailVerdict:
    status = r["status"]
    reason = r["review_reason"]
    return EmailVerdict(
        category=r["category"],
        status=status,
        review_reason=reason,
        has_defect=bool(r["has_defect"]),
        defect_fields=json.loads(r["defect_fields_json"] or "[]"),
    )


def normalized_pair_key(left: str, right: str) -> str:
    a = " ".join(left.upper().split())
    b = " ".join(right.upper().split())
    pair = sorted([a, b])
    return f"{pair[0]}||{pair[1]}"
