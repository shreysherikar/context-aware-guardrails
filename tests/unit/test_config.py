"""Focused tests for environment-driven configuration."""

from domain.enums import PolicyAction, RiskLevel
from domain.models import AuditEvent, PolicyDecision, RiskAssessment
from services.audit.audit import log_event


def test_audit_db_path_reads_from_environment(monkeypatch, tmp_path):
    target = tmp_path / "custom_audit.db"
    monkeypatch.setenv("AUDIT_DB_PATH", str(target))

    log_event(
        AuditEvent(
            conversation_id="cfg",
            prompt="hello",
            user_role="researcher",
            risk_assessment=RiskAssessment(risk_level=RiskLevel.LOW),
            policy_decision=PolicyDecision(
                action=PolicyAction.ALLOW, policy_id="LOW-001", policy_version="0.1.0"
            ),
        )
    )
    assert target.exists()
