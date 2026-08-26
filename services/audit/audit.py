"""
Audit log (services/audit).

Every request — regardless of outcome — is logged here. This is a
protected data asset in its own right (it will contain the same PII/PHI
that appears in flagged prompts), so treat access to audit.db accordingly.
Swap sqlite3 for a production database when the production/security layer
is built without touching callers — they only ever call log_event().
"""

import os
import sqlite3
from pathlib import Path

from domain.models import AuditEvent

DB_PATH = Path(__file__).resolve().parents[2] / "audit.db"

# Columns added to audit_log after the initial schema existed. Each entry is a
# (column_name, column_type) pair; _get_conn() adds any that are missing on
# every connection open so pre-existing audit.db files keep working instead of
# crashing INSERT with "no such column". Identifiers come from this module-level
# constant only — never from user input.
_COLUMNS_TO_MIGRATE: list[tuple[str, str]] = [
    ("llm", "TEXT"),
    ("output_guardrail", "TEXT"),
    ("optical", "TEXT"),
    ("sanitization", "TEXT"),
]


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Add any expected audit_log columns that are missing (idempotent).

    CREATE TABLE IF NOT EXISTS is a no-op against an already-existing table, so
    databases created before a column was introduced would otherwise fail on
    every insert. The PRAGMA check is cheap; ALTER TABLE runs only for columns
    that are actually absent.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)")}
    for name, column_type in _COLUMNS_TO_MIGRATE:
        if name not in existing:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {name} {column_type}")


def _get_conn() -> sqlite3.Connection:
    # AUDIT_DB_PATH is read per connection so the location is configurable
    # (e.g. a volume path in Docker) without code changes.
    db_path = Path(os.getenv("AUDIT_DB_PATH", str(DB_PATH)))
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            user_role TEXT NOT NULL,
            risk_assessment TEXT NOT NULL,
            policy_decision TEXT NOT NULL,
            llm TEXT,
            output_guardrail TEXT,
            optical TEXT,
            sanitization TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )
    _add_missing_columns(conn)
    return conn


def log_event(event: AuditEvent) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO audit_log
               (conversation_id, prompt, user_role, risk_assessment,
                policy_decision, llm, output_guardrail, optical, sanitization,
                timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.conversation_id,
                event.prompt,
                event.user_role,
                event.risk_assessment.model_dump_json(),
                event.policy_decision.model_dump_json(),
                event.llm.model_dump_json() if event.llm else None,
                event.output_guardrail.model_dump_json() if event.output_guardrail else None,
                event.optical.model_dump_json() if event.optical else None,
                event.sanitization.model_dump_json() if event.sanitization else None,
                event.timestamp.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
