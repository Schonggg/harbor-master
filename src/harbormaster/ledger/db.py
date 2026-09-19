"""SQLite locally, Postgres (Supabase) when DATABASE_URL is postgresql://."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Any, Iterator, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def postgres_dsn() -> str | None:
    if "DATABASE_URL" in os.environ:
        raw = (os.environ.get("DATABASE_URL") or "").strip()
    else:
        try:
            from harbormaster.config import get_settings

            raw = (get_settings().database_url or "").strip()
        except Exception:
            raw = ""
    if raw.startswith("postgres://") or raw.startswith("postgresql://"):
        return _prepare_dsn(raw)
    return None


def is_postgres() -> bool:
    return postgres_dsn() is not None


def public_db_label() -> str:
    """Safe label for /health — never includes the password."""
    dsn = postgres_dsn()
    if not dsn:
        from harbormaster.config import db_path

        return str(db_path())
    parsed = urlparse(dsn)
    host = parsed.hostname or "postgres"
    db = (parsed.path or "/postgres").lstrip("/") or "postgres"
    return f"postgres://{host}/{db}"


def redact_error(text: str) -> str:
    return re.sub(r"(postgres(?:ql)?://[^:/]+:)[^@/]+@", r"\1***@", text, flags=re.I)


def _prepare_dsn(dsn: str) -> str:
    parsed = urlparse(dsn)
    password = parsed.password or ""
    if len(password) > 2 and password.startswith("[") and password.endswith("]"):
        user = parsed.username or ""
        host = parsed.hostname or ""
        port = parsed.port
        auth = f"{user}:{password[1:-1]}"
        netloc = f"{auth}@{host}" + (f":{port}" if port else "")
        parsed = parsed._replace(netloc=netloc)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    return urlunparse(parsed._replace(query=urlencode(query)))


def adapt_sql(sql: str) -> str:
    return sql.replace("?", "%s")


def split_statements(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                parts.append(stmt)
            buf = []
    tail = "\n".join(buf).strip().rstrip(";").strip()
    if tail:
        parts.append(tail)
    return parts


class PgCursor:
    def __init__(self, cur: Any) -> None:
        self._cur = cur

    def fetchone(self) -> Any:
        return self._cur.fetchone()

    def fetchall(self) -> list[Any]:
        return list(self._cur.fetchall())

    @property
    def rowcount(self) -> int:
        return int(self._cur.rowcount or 0)


class PgConn:
    """sqlite3-shaped wrapper: execute(sql, params) with ? placeholders."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Sequence[Any] = ()) -> PgCursor:
        return PgCursor(self._conn.execute(adapt_sql(sql), tuple(params)))

    def executescript(self, sql: str) -> PgConn:
        for stmt in split_statements(sql):
            self._conn.execute(stmt)
        return self

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


@contextmanager
def connect_postgres(dsn: str) -> Iterator[PgConn]:
    import time

    import psycopg
    from psycopg.rows import dict_row

    conn = None
    last: Exception | None = None
    for attempt in range(4):
        try:
            conn = psycopg.connect(
                dsn,
                row_factory=dict_row,
                prepare_threshold=None,
                connect_timeout=15,
            )
            break
        except Exception as exc:  # noqa: BLE001 — paused pooler wakes on retry
            last = exc
            time.sleep(0.7 * (attempt + 1))
    if conn is None:
        raise last or RuntimeError("postgres connect failed")
    try:
        yield PgConn(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
