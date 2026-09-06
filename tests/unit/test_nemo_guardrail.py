"""Unit tests for NeMo Guardrails integration (stub backend — no SDK required)."""

from __future__ import annotations

import asyncio

import pytest

from domain.enums import PolicyAction, RiskCategory, RiskLevel
from domain.models import GuardrailRequest, OutputAssessment, RiskAssessment
from services.nemo_guardrail.client import NeMoGuardrailsClient
from services.nemo_guardrail.dialog_rail import NeMoDialogRail
from services.nemo_guardrail.input_rail import NeMoInputRail
from services.nemo_guardrail.models import NeMoRailOutcome, NeMoRailStatus
from services.nemo_guardrail.normalizer import (
    merge_nemo_into_risk,
    normalize_input_status,
    normalize_output_status,
    outcome_to_output_assessment,
)
from services.nemo_guardrail.output_rail import NeMoOutputGuardrail


class StubBackend:
    """Configurable stub for NeMo rail checks."""

    def __init__(self, outcome: NeMoRailOutcome) -> None:
        self.outcome = outcome
        self.last_messages: list[dict[str, str]] | None = None

    async def check_input(self, text: str) -> NeMoRailOutcome:
        return self.outcome

    async def check_output(self, prompt: str, generated_text: str) -> NeMoRailOutcome:
        return self.outcome

    async def check_dialog(self, messages: list[dict[str, str]]) -> NeMoRailOutcome:
        self.last_messages = messages
        return self.outcome


def _base_risk() -> RiskAssessment:
    return RiskAssessment(
        risk_level=RiskLevel.LOW,
        categories=[RiskCategory.NONE],
        confidence=0.8,
        reasoning="baseline classifier",
    )


def _run(coro):
    return asyncio.run(coro)


def test_normalize_input_blocked():
    outcome = normalize_input_status(
        status="BLOCKED",
        content="refused",
        original="hack the system",
    )
    assert outcome.status == NeMoRailStatus.BLOCKED
    assert outcome.suggested_action == PolicyAction.BLOCK


def test_normalize_input_fail_closed():
    outcome = normalize_input_status(
        status="",
        content="",
        original="hello",
        fail_closed=True,
    )
    assert outcome.status == NeMoRailStatus.INDETERMINATE
    assert outcome.fail_closed is True
    assert outcome.suggested_action == PolicyAction.REVIEW


def test_merge_blocked_escalates_risk():
    outcome = NeMoRailOutcome(
        status=NeMoRailStatus.BLOCKED,
        suggested_action=PolicyAction.BLOCK,
    )
    merged = merge_nemo_into_risk(_base_risk(), outcome)
    assert merged.risk_level == RiskLevel.CRITICAL
    assert merged.injection_detected is True
    assert RiskCategory.PROMPT_INJECTION in merged.categories
    assert "NeMo" not in merged.reasoning
    assert "defense-in-depth" in merged.reasoning.lower()


def test_merge_indeterminate_fail_closed_to_review_path():
    outcome = NeMoRailOutcome(
        status=NeMoRailStatus.INDETERMINATE,
        fail_closed=True,
        suggested_action=PolicyAction.REVIEW,
    )
    merged = merge_nemo_into_risk(_base_risk(), outcome)
    assert merged.risk_level == RiskLevel.CRITICAL
    assert merged.injection_detected is False
    assert "defense-in-depth" in merged.reasoning.lower()


def test_merge_modified_suggests_rewrite_signals():
    outcome = NeMoRailOutcome(
        status=NeMoRailStatus.MODIFIED,
        content="[REDACTED]",
        suggested_action=PolicyAction.REWRITE,
        rewrite_applied=True,
    )
    merged = merge_nemo_into_risk(_base_risk(), outcome)
    assert merged.risk_level == RiskLevel.MEDIUM
    assert RiskCategory.PII in merged.categories


def test_output_assessment_blocked():
    outcome = NeMoRailOutcome(status=NeMoRailStatus.BLOCKED, suggested_action=PolicyAction.BLOCK)
    assessment = outcome_to_output_assessment(outcome)
    assert assessment.flagged is True
    assert assessment.blocked is True
    assert "NeMo" not in assessment.reasoning


def test_output_assessment_modified_rewrite():
    outcome = NeMoRailOutcome(
        status=NeMoRailStatus.MODIFIED,
        content="safe version",
        rewrite_applied=True,
        suggested_action=PolicyAction.REWRITE,
    )
    assessment = outcome_to_output_assessment(outcome)
    assert assessment.flagged is False
    assert assessment.safe_text == "safe version"
    assert assessment.rewrite_applied is True


def test_output_assessment_indeterminate_raises():
    outcome = NeMoRailOutcome(
        status=NeMoRailStatus.INDETERMINATE,
        fail_closed=True,
        suggested_action=PolicyAction.REVIEW,
    )
    with pytest.raises(RuntimeError):
        outcome_to_output_assessment(outcome)


def test_input_rail_augment_risk():
    backend = StubBackend(
        NeMoRailOutcome(status=NeMoRailStatus.BLOCKED, suggested_action=PolicyAction.BLOCK)
    )
    rail = NeMoInputRail(NeMoGuardrailsClient(backend))
    request = GuardrailRequest(prompt="ignore instructions", conversation_id="c1")
    merged = rail.augment_risk(request, _base_risk())
    assert merged.risk_level == RiskLevel.CRITICAL


def test_input_rail_fail_closed_on_backend_error():
    class FailingBackend:
        async def check_input(self, text: str) -> NeMoRailOutcome:
            raise RuntimeError("sdk down")

        async def check_output(self, prompt: str, generated_text: str) -> NeMoRailOutcome:
            raise RuntimeError("sdk down")

        async def check_dialog(self, messages: list[dict[str, str]]) -> NeMoRailOutcome:
            raise RuntimeError("sdk down")

    rail = NeMoInputRail(NeMoGuardrailsClient(FailingBackend()))
    request = GuardrailRequest(prompt="hello", conversation_id="c1")
    merged = rail.augment_risk(request, _base_risk())
    assert merged.risk_level == RiskLevel.CRITICAL
    assert merged.injection_detected is False


def test_output_guardrail_check():
    backend = StubBackend(
        NeMoRailOutcome(status=NeMoRailStatus.PASSED, suggested_action=PolicyAction.ALLOW)
    )
    guard = NeMoOutputGuardrail(NeMoGuardrailsClient(backend))
    result = _run(guard.check("prompt", "generated"))
    assert isinstance(result, OutputAssessment)
    assert result.flagged is False


def test_output_guardrail_fail_closed_raises():
    backend = StubBackend(
        NeMoRailOutcome(
            status=NeMoRailStatus.INDETERMINATE,
            fail_closed=True,
            suggested_action=PolicyAction.REVIEW,
        )
    )
    guard = NeMoOutputGuardrail(NeMoGuardrailsClient(backend))
    with pytest.raises(RuntimeError):
        _run(guard.check("prompt", "generated"))


def test_dialog_rail_includes_history():
    backend = StubBackend(
        NeMoRailOutcome(status=NeMoRailStatus.PASSED, suggested_action=PolicyAction.ALLOW)
    )
    rail = NeMoDialogRail(NeMoGuardrailsClient(backend))
    rail.record_assistant_turn("conv-1", "prior answer")
    request = GuardrailRequest(prompt="follow up", conversation_id="conv-1")
    merged = rail.augment_risk(request, _base_risk())
    assert merged.risk_level == RiskLevel.LOW
    assert backend.last_messages is not None
    assert backend.last_messages[0]["role"] == "assistant"
    assert backend.last_messages[-1]["content"] == "follow up"


def test_normalize_output_status_blocked():
    outcome = normalize_output_status(
        status="BLOCKED",
        content="blocked output",
        original="unsafe output",
    )
    assert outcome.status == NeMoRailStatus.BLOCKED
    assert outcome.suggested_action == PolicyAction.BLOCK


def test_factory_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NEMO_GUARDRAILS_ENABLED", raising=False)
    from services.nemo_guardrail.factory import get_nemo_input_rail, is_nemo_enabled

    assert is_nemo_enabled() is False
    assert get_nemo_input_rail() is None


def test_factory_enabled_when_flag_set(monkeypatch):
    monkeypatch.setenv("NEMO_GUARDRAILS_ENABLED", "true")
    monkeypatch.setenv("NEMO_GUARDRAILS_MODE", "input")
    from services.nemo_guardrail import factory

    factory._client.cache_clear()
    rail = factory.get_nemo_input_rail()
    assert rail is not None
    factory._client.cache_clear()
