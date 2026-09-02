"""Unit tests for agent feedback builder."""

from typing import Any

from domain.enums import DataSensitivity, PolicyAction, RiskCategory, RiskLevel
from domain.models import RiskAssessment
from services.agent.feedback import build_corrections, build_issues, compose_deterministic_message


def _risk(**kwargs) -> RiskAssessment:
    defaults: dict[str, Any] = dict(
        risk_level=RiskLevel.MEDIUM,
        categories=[RiskCategory.PII],
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
        confidence=0.8,
        reasoning="test",
    )
    defaults.update(kwargs)
    return RiskAssessment(**defaults)


def test_build_issues_pii():
    issues = build_issues(_risk())
    assert any(i.code == "PII" for i in issues)


def test_build_issues_injection():
    issues = build_issues(
        _risk(
            categories=[RiskCategory.PROMPT_INJECTION],
            injection_detected=True,
            risk_level=RiskLevel.CRITICAL,
        )
    )
    assert any(i.code == "PROMPT_INJECTION" for i in issues)


def test_build_corrections_block():
    issues = build_issues(
        _risk(categories=[RiskCategory.PROMPT_INJECTION], injection_detected=True)
    )
    fixes = build_corrections(PolicyAction.BLOCK, issues)
    assert len(fixes) >= 1


def test_compose_message_rewrite_includes_sanitized():
    msg = compose_deterministic_message(
        action=PolicyAction.REWRITE,
        issues=build_issues(_risk()),
        corrections=build_corrections(PolicyAction.REWRITE, build_issues(_risk())),
        answer="Here is a summary.",
        sanitized_text="SSN [REDACTED]",
    )
    assert "redacted" in msg.lower() or "SSN [REDACTED]" in msg
    assert "Here is a summary." in msg


def test_compose_message_block_no_answer():
    issues = build_issues(
        _risk(categories=[RiskCategory.PROMPT_INJECTION], injection_detected=True)
    )
    msg = compose_deterministic_message(
        action=PolicyAction.BLOCK,
        issues=issues,
        corrections=build_corrections(PolicyAction.BLOCK, issues),
        answer="should not appear",
    )
    assert "should not appear" not in msg
    assert "not able to help" in msg.lower() or "policy" in msg.lower()
