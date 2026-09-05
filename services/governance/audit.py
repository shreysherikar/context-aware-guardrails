"""Append-only governance audit log."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from domain.governance_models import GovernanceAuditRecord
from services import db

DB_PATH = Path(__file__).resolve().parents[2] / "governance_audit.db"


class GovernanceAuditStore:
    """Append-only audit store — agents cannot modify or delete records."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or Path(os.getenv("GOVERNANCE_AUDIT_DB_PATH", str(DB_PATH)))
        self._ensure_schema()

    def _get_conn(self) -> db.Connection:
        conn = db.get_connection(self._db_path)
        if not db.is_postgres():
            # PRAGMA journal_mode is SQLite-only; in PostgreSQL mode the shared
            # database handles durability itself.
            conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS governance_audit (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    record_json TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def append(self, record: GovernanceAuditRecord) -> str:
        audit_id = str(uuid.uuid4())
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO governance_audit (id, timestamp, record_json) VALUES (?, ?, ?)",
                (audit_id, record.timestamp.isoformat(), record.model_dump_json()),
            )
            conn.commit()
        finally:
            conn.close()
        return audit_id

    def list_recent(self, limit: int = 50) -> list[GovernanceAuditRecord]:
        limit = max(1, min(limit, 200))
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT record_json FROM governance_audit ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [GovernanceAuditRecord.model_validate_json(r[0]) for r in rows]

    def count(self) -> int:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT COUNT(*) FROM governance_audit").fetchone()
        finally:
            conn.close()
        return row[0] if row else 0

    @property
    def available(self) -> bool:
        try:
            self._ensure_schema()
            return True
        except Exception:
            return False
