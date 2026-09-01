"""Tests for conversational guardrail display helpers."""

from domain.enums import PolicyAction
from services.agent.feedback import (
    build_prompt_highlights,
    guardrail_was_triggered,
    issues_for_display,
)
from services.agent.models import AgentIssue


def test_clean_allow_hides_issues():
    issues = [
        AgentIssue(code="OPTICAL_SCAN", title="Scan", description="Scanned", severity="low"),
    ]
    assert issues_for_display(PolicyAction.ALLOW, issues) == []


def test_block_shows_issues():
    issues = [
        AgentIssue(
            code="PROMPT_INJECTION",
            title="Injection",
            description="Bypass attempt",
            severity="high",
        ),
    ]
    shown = issues_for_display(PolicyAction.BLOCK, issues)
    assert len(shown) == 1


def test_guardrail_not_triggered_on_clean_allow():
    assert guardrail_was_triggered(PolicyAction.ALLOW, []) is False


def test_guardrail_triggered_on_block():
    issues = [AgentIssue(code="X", title="T", description="D")]
    assert guardrail_was_triggered(PolicyAction.BLOCK, issues, blocked=True) is True


def test_highlights_ssn():
    text = "Please use SSN 123-45-6789 for payroll."
    highlights = build_prompt_highlights(
        text,
        [AgentIssue(code="PII", title="PII", description="SSN detected")],
    )
    assert len(highlights) >= 1
    joined = " ".join(h.text for h in highlights)
    assert "123-45-6789" in joined or "SSN" in joined
