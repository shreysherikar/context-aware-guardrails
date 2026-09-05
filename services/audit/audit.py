"""
Audit log (services/audit).

Every request — regardless of outcome — is logged here. This is a
protected data asset in its own right (it will contain the same PII/PHI
that appears in flagged prompts), so treat access accordingly. By default
the log lives in audit.db (SQLite); set DATABASE_URL to back this module —
and the other storage modules — with a shared PostgreSQL database instead.
Callers only ever call log_event().
"""

import os
from datetime import datetime
from pathlib import Path

from domain.models import (
    AuditEvent,
    ClaimVerificationMeta,
    LLMResult,
    OpticalAuditMeta,
    OutputGuardrailResult,
    PolicyDecision,
    RiskAssessment,
    SanitizationAuditMeta,
)
from services import db

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
    ("claim_verification", "TEXT"),
    ("request_id", "TEXT"),
    ("resolution_type", "TEXT"),
    ("forwarded_to_llm", "INTEGER"),
    ("sanitization_occurred", "INTEGER"),
    ("human_review_requested", "INTEGER"),
    ("human_review_outcome", "TEXT"),
    ("report_status", "TEXT"),
]

_AUDIT_SELECT = """SELECT conversation_id, prompt, user_role, risk_assessment,
                   policy_decision, llm, output_guardrail, optical, sanitization,
                   claim_verification, request_id, resolution_type, forwarded_to_llm,
                   sanitization_occurred, human_review_requested, human_review_outcome,
                   report_status, timestamp
                   FROM audit_log"""


_AUDIT_CREATE_SQLITE = """
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
    claim_verification TEXT,
    request_id TEXT,
    resolution_type TEXT,
    forwarded_to_llm INTEGER,
    sanitization_occurred INTEGER,
    human_review_requested INTEGER,
    human_review_outcome TEXT,
    report_status TEXT,
    timestamp TEXT NOT NULL
)
"""

# Same columns as the SQLite schema; only the id generation syntax differs
# (SERIAL == INTEGER PRIMARY KEY AUTOINCREMENT). TEXT/INTEGER are valid on both.
_AUDIT_CREATE_PG = """
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    user_role TEXT NOT NULL,
    risk_assessment TEXT NOT NULL,
    policy_decision TEXT NOT NULL,
    llm TEXT,
    output_guardrail TEXT,
    optical TEXT,
    sanitization TEXT,
    claim_verification TEXT,
    request_id TEXT,
    resolution_type TEXT,
    forwarded_to_llm INTEGER,
    sanitization_occurred INTEGER,
    human_review_requested INTEGER,
    human_review_outcome TEXT,
    report_status TEXT,
    timestamp TEXT NOT NULL
)
"""


def _add_missing_columns(conn: db.Connection) -> None:
    """Add any expected audit_log columns that are missing (idempotent).

    CREATE TABLE IF NOT EXISTS is a no-op against an already-existing table, so
    databases created before a column was introduced would otherwise fail on
    every insert. Existing columns are checked cheaply on every connection open
    (PRAGMA table_info on SQLite, information_schema on PostgreSQL) and ALTER
    TABLE runs only for columns that are actually absent.
    """
    existing = db.existing_columns(conn, "audit_log")
    for name, column_type in _COLUMNS_TO_MIGRATE:
        if name not in existing:
            conn.execute(f"ALTER TABLE audit_log ADD COLUMN {name} {column_type}")


def _get_conn() -> db.Connection:
    # AUDIT_DB_PATH is read per connection so the location is configurable
    # (e.g. a volume path in Docker) without code changes. When DATABASE_URL is
    # set the shared PostgreSQL database replaces the local file entirely.
    db_path = Path(os.getenv("AUDIT_DB_PATH", str(DB_PATH)))
    conn = db.get_connection(db_path)
    if db.is_postgres():
        # PostgreSQL DDL is transactional: persist CREATE TABLE / ALTER TABLE so
        # the next (separate) connection sees them.
        conn.execute(_AUDIT_CREATE_PG)
        _add_missing_columns(conn)
        conn.commit()
    else:
        conn.execute(_AUDIT_CREATE_SQLITE)
        _add_missing_columns(conn)
    return conn


def log_event(event: AuditEvent) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO audit_log
               (conversation_id, prompt, user_role, risk_assessment,
                policy_decision, llm, output_guardrail, optical, sanitization,
                claim_verification, request_id, resolution_type, forwarded_to_llm,
                sanitization_occurred, human_review_requested, human_review_outcome,
                report_status, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                event.claim_verification.model_dump_json() if event.claim_verification else None,
                event.request_id or None,
                event.resolution_type,
                1 if event.forwarded_to_llm else 0,
                1 if event.sanitization_occurred else 0,
                1 if event.human_review_requested else 0,
                event.human_review_outcome,
                event.report_status,
                event.timestamp.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_audit_event(row: tuple) -> AuditEvent:
    """Deserialize one audit_log row into an AuditEvent."""
    (
        conversation_id,
        prompt,
        user_role,
        risk_assessment_json,
        policy_decision_json,
        llm_json,
        output_guardrail_json,
        optical_json,
        sanitization_json,
        claim_verification_json,
        request_id,
        resolution_type,
        forwarded_to_llm,
        sanitization_occurred,
        human_review_requested,
        human_review_outcome,
        report_status,
        timestamp,
    ) = row
    return AuditEvent(
        conversation_id=conversation_id,
        prompt=prompt,
        user_role=user_role,
        risk_assessment=RiskAssessment.model_validate_json(risk_assessment_json),
        policy_decision=PolicyDecision.model_validate_json(policy_decision_json),
        llm=LLMResult.model_validate_json(llm_json) if llm_json else None,
        output_guardrail=OutputGuardrailResult.model_validate_json(output_guardrail_json)
        if output_guardrail_json
        else None,
        optical=OpticalAuditMeta.model_validate_json(optical_json) if optical_json else None,
        sanitization=SanitizationAuditMeta.model_validate_json(sanitization_json)
        if sanitization_json
        else None,
        claim_verification=ClaimVerificationMeta.model_validate_json(claim_verification_json)
        if claim_verification_json
        else None,
        request_id=request_id or "",
        resolution_type=resolution_type,
        forwarded_to_llm=bool(forwarded_to_llm),
        sanitization_occurred=bool(sanitization_occurred),
        human_review_requested=bool(human_review_requested),
        human_review_outcome=human_review_outcome,
        report_status=report_status,
        timestamp=datetime.fromisoformat(timestamp),
    )


def get_recent_events(conversation_id: str, limit: int = 10) -> list[AuditEvent]:
    """Return the MOST RECENT ``limit`` prior audit events, oldest first.

    Used by the trajectory engine: a long conversation must be scored on its
    latest turns, so the query selects the newest ``limit`` rows (descending)
    and they are returned in chronological order (oldest -> newest) so trend
    calculation sees time-ordered turns. Only prior turns are returned: for a
    live request the current turn's event is written by log_event() AFTER the
    policy decision is made, so at the point trajectory evaluation runs the
    current turn has not been persisted and this query structurally cannot
    include it.
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            f"""{_AUDIT_SELECT}
               WHERE conversation_id = ?
               ORDER BY id DESC
               LIMIT ?""",
            (conversation_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_audit_event(row) for row in reversed(rows)]


def list_events(conversation_id: str | None = None, limit: int = 50) -> list[AuditEvent]:
    """Read-only listing for the audit viewer UI. Newest first."""
    limit = max(1, min(limit, 200))
    conn = _get_conn()
    try:
        if conversation_id is not None:
            rows = conn.execute(
                f"""{_AUDIT_SELECT}
                   WHERE conversation_id = ?
                   ORDER BY id DESC
                   LIMIT ?""",
                (conversation_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""{_AUDIT_SELECT}
                   ORDER BY id DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    return [_row_to_audit_event(row) for row in rows]
