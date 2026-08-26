"""Regression tests for in-place audit schema migration.

A pre-existing audit.db created before a column was added used to crash every
log_event() call with "table audit_log has no column named ...", because
CREATE TABLE IF NOT EXISTS is a no-op against an existing table. These tests
create databases with those older schemas and prove log_event() migrates them
in place and writes rows correctly.
"""

import json
import sqlite3

from domain.enums import PolicyAction, RiskLevel
from domain.models import (
    AuditEvent,
    OutputGuardrailResult,
    PolicyDecision,
    RiskAssessment,
)
from services.audit.audit import log_event


def _make_event(
    conversation_id: str = "mig",
    output_guardrail: OutputGuardrailResult | None = None,
) -> AuditEvent:
    return AuditEvent(
        conversation_id=conversation_id,
        prompt="hello",
        user_role="researcher",
        risk_assessment=RiskAssessment(risk_level=RiskLevel.LOW),
        policy_decision=PolicyDecision(
            action=PolicyAction.ALLOW, policy_id="LOW-001", policy_version="0.1.0"
        ),
        llm=None,
        output_guardrail=output_guardrail,
    )


def _create_old_schema_db(path) -> None:
    """Schema as it existed before the output_guardrail column was added."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            user_role TEXT NOT NULL,
            risk_assessment TEXT NOT NULL,
            policy_decision TEXT NOT NULL,
            llm TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _columns(db_path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info(audit_log)")]
    finally:
        conn.close()


def test_pre_output_guardrail_schema_is_migrated_and_row_written(monkeypatch, tmp_path):
    target = tmp_path / "old_audit.db"
    _create_old_schema_db(target)
    assert "output_guardrail" not in _columns(target)

    monkeypatch.setenv("AUDIT_DB_PATH", str(target))
    # Must not raise sqlite3.OperationalError ("no column named output_guardrail").
    result = OutputGuardrailResult(attempted=True, flagged=True, error_kind="RuntimeError")
    log_event(_make_event("mig-1", output_guardrail=result))

    # The missing column was added in place...
    assert "output_guardrail" in _columns(target)

    # ...and the row was written with the correct serialized value.
    check = sqlite3.connect(target)
    try:
        row = check.execute("SELECT conversation_id, output_guardrail FROM audit_log").fetchone()
        assert row[0] == "mig-1"
        assert json.loads(row[1]) == {
            "attempted": True,
            "flagged": True,
            "error_kind": "RuntimeError",
        }
    finally:
        check.close()


def test_migration_is_idempotent_across_repeated_calls(monkeypatch, tmp_path):
    target = tmp_path / "old_audit.db"
    _create_old_schema_db(target)
    monkeypatch.setenv("AUDIT_DB_PATH", str(target))

    # A second connection open must not attempt to re-add an existing column.
    log_event(_make_event("mig-a"))
    log_event(_make_event("mig-b"))

    check = sqlite3.connect(target)
    try:
        count = check.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        assert count == 2
    finally:
        check.close()


def test_older_schema_missing_llm_column_migrates_both_columns(monkeypatch, tmp_path):
    """The generic helper adds every missing expected column, in sequence."""
    target = tmp_path / "older_audit.db"
    conn = sqlite3.connect(target)
    conn.execute(
        """
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            user_role TEXT NOT NULL,
            risk_assessment TEXT NOT NULL,
            policy_decision TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("AUDIT_DB_PATH", str(target))
    log_event(
        _make_event(
            "mig-old",
            output_guardrail=OutputGuardrailResult(attempted=False, flagged=False),
        )
    )

    columns = _columns(target)
    assert "llm" in columns
    assert "output_guardrail" in columns
    assert "optical" in columns


def test_pre_optical_schema_is_migrated(monkeypatch, tmp_path):
    """Schema with llm + output_guardrail but without optical still migrates."""
    target = tmp_path / "pre_optical.db"
    conn = sqlite3.connect(target)
    conn.execute(
        """
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            user_role TEXT NOT NULL,
            risk_assessment TEXT NOT NULL,
            policy_decision TEXT NOT NULL,
            llm TEXT,
            output_guardrail TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    assert "optical" not in _columns(target)

    monkeypatch.setenv("AUDIT_DB_PATH", str(target))
    from domain.models import OpticalAuditMeta

    log_event(
        AuditEvent(
            conversation_id="mig-opt",
            prompt="[image input]",
            user_role="researcher",
            risk_assessment=RiskAssessment(risk_level=RiskLevel.LOW),
            policy_decision=PolicyDecision(
                action=PolicyAction.ALLOW, policy_id="LOW-001", policy_version="0.1.0"
            ),
            optical=OpticalAuditMeta(
                input_type="image",
                ocr_used=True,
                optical_analysis_used=True,
                finding_count=0,
                image_sha256="abc",
            ),
        )
    )

    assert "optical" in _columns(target)
    check = sqlite3.connect(target)
    try:
        row = check.execute("SELECT optical FROM audit_log").fetchone()
        assert json.loads(row[0])["input_type"] == "image"
        assert json.loads(row[0])["image_sha256"] == "abc"
    finally:
        check.close()
