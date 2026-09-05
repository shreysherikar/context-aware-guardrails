"""Backend-agnostic database access for the storage modules.

The three storage modules (services/audit/audit.py, services/governance/audit.py,
services/guardrail_review/store.py) share this single connection helper so that
one PostgreSQL database (DATABASE_URL) can back them in production while local
development keeps the existing SQLite files exactly as before.

- ``DATABASE_URL`` set   -> PostgreSQL via psycopg; all three modules share one
  database (tables: audit_log, governance_audit, evaluation_snapshots,
  review_requests, decision_reports).
- ``DATABASE_URL`` unset -> plain ``sqlite3`` connections to each module's local
  file (the unchanged fallback used by local dev and the test suite).
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

# psycopg uses %s placeholders while the storage modules' SQL is written with
# sqlite3's ? so the query text can be shared verbatim between backends. No
# module query embeds a literal '?' inside a string literal, so the translation
# below is safe for everything the storage modules execute.
_SQLITE_PLACEHOLDER = re.compile(r"\?")
_DATABASE_URL_ENV = "DATABASE_URL"


class PostgresConnection:
    """A psycopg connection exposing the sqlite3-style surface modules expect.

    ``execute()`` translates ``?`` placeholders to psycopg's ``%s`` and returns
    the psycopg cursor (which supports the same fetchone()/fetchall() calls the
    modules already use). ``commit()`` and ``close()`` delegate directly.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | None = None):
        return self._conn.execute(_SQLITE_PLACEHOLDER.sub("%s", sql), params or ())

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# The connection surface every storage module relies on: execute/commit/close.
Connection = sqlite3.Connection | PostgresConnection


def is_postgres() -> bool:
    """True when DATABASE_URL is set (PostgreSQL mode)."""
    return bool(os.getenv(_DATABASE_URL_ENV))


def get_connection(db_path: Path | str | None = None) -> Connection:
    """Open a connection to the configured backend.

    With ``DATABASE_URL`` set this returns a :class:`PostgresConnection` to the
    single shared PostgreSQL database (``db_path`` is ignored). Otherwise it
    returns a plain ``sqlite3.Connection`` to ``db_path`` — the per-module local
    fallback.
    """
    url = os.getenv(_DATABASE_URL_ENV)
    if url:
        # psycopg is imported lazily so the SQLite fallback keeps working in
        # environments where the PostgreSQL driver is not (yet) installed.
        import psycopg

        return PostgresConnection(psycopg.connect(url))
    if db_path is None:
        raise ValueError("db_path is required when DATABASE_URL is not set")
    return sqlite3.connect(db_path)


def existing_columns(conn: Connection, table: str) -> set[str]:
    """Return the existing column names for ``table`` (backend-agnostic).

    SQLite reports them via ``PRAGMA table_info``; PostgreSQL via
    ``information_schema.columns``. ``table`` is always a module-level constant
    in the calling storage module — never user input.
    """
    if is_postgres():
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (table,),
        ).fetchall()
        return {row[0] for row in rows}
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}
