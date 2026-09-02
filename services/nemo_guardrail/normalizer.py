"""Normalize NeMo rail outcomes into ContextGuard domain signals."""

from __future__ import annotations

from domain.enums import DataSensitivity, PolicyAction, RiskCategory, RiskLevel
from domain.models import OutputAssessment, RiskAssessment
from services.nemo_guardrail.models import NeMoRailOutcome, NeMoRailStatus

_RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.NONE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}

_SENSITIVITY_RANK: dict[DataSensitivity, int] = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.CONFIDENTIAL: 2,
    DataSensitivity.PATIENT_IDENTIFIABLE: 3,
}

# Generic internal suffix — never names NeMo, Colang, or rail identifiers.
_FAIL_CLOSED_SUFFIX = (
    "An additional defense-in-depth safety check could not complete; treating as high risk."
)
_BLOCKED_SUFFIX = "Blocked by an additional defense-in-depth safety check."
_MODIFIED_SUFFIX = "Modified by an additional defense-in-depth safety check."


def normalize_input_status(
    *,
    status: str,
    content: str,
    original: str,
    fail_closed: bool = False,
) -> NeMoRailOutcome:
    """Map a raw NeMo check status string onto NeMoRailOutcome."""
    if fail_closed:
        return NeMoRailOutcome(
            status=NeMoRailStatus.INDETERMINATE,
            content=original,
            suggested_action=PolicyAction.REVIEW,
            fail_closed=True,
            internal_reason="rail check failed or timed out",
        )

    normalized = status.upper()
    if normalized == "BLOCKED":
        return NeMoRailOutcome(
            status=NeMoRailStatus.BLOCKED,
            content=content or original,
            suggested_action=PolicyAction.BLOCK,
            internal_reason="input blocked",
        )
    if normalized == "MODIFIED":
        return NeMoRailOutcome(
            status=NeMoRailStatus.MODIFIED,
            content=content or original,
            suggested_action=PolicyAction.REWRITE,
            rewrite_applied=content != original,
            internal_reason="input modified",
        )
    return NeMoRailOutcome(
        status=NeMoRailStatus.PASSED,
        content=content or original,
        suggested_action=PolicyAction.ALLOW,
    )


def normalize_output_status(
    *,
    status: str,
    content: str,
    original: str,
    fail_closed: bool = False,
) -> NeMoRailOutcome:
    """Map a raw NeMo output check onto NeMoRailOutcome."""
    if fail_closed:
        return NeMoRailOutcome(
            status=NeMoRailStatus.INDETERMINATE,
            content=original,
            suggested_action=PolicyAction.REVIEW,
            fail_closed=True,
            internal_reason="output rail check failed or timed out",
        )

    normalized = status.upper()
    if normalized == "BLOCKED":
        return NeMoRailOutcome(
            status=NeMoRailStatus.BLOCKED,
            content=content or original,
            suggested_action=PolicyAction.BLOCK,
            internal_reason="output blocked",
        )
    if normalized == "MODIFIED":
        return NeMoRailOutcome(
            status=NeMoRailStatus.MODIFIED,
            content=content or original,
            suggested_action=PolicyAction.REWRITE,
            rewrite_applied=content != original,
            internal_reason="output modified",
        )
    return NeMoRailOutcome(
        status=NeMoRailStatus.PASSED,
        content=content or original,
        suggested_action=PolicyAction.ALLOW,
    )


def outcome_to_output_assessment(outcome: NeMoRailOutcome) -> OutputAssessment:
    """Convert a normalized NeMo output outcome into OutputAssessment."""
    if outcome.fail_closed or outcome.status == NeMoRailStatus.INDETERMINATE:
        raise RuntimeError("NeMo output rail indeterminate — fail closed to REVIEW")

    if outcome.status == NeMoRailStatus.BLOCKED:
        return OutputAssessment(
            flagged=True,
            blocked=True,
            reasoning="Post-generation safety check blocked the response.",
            confidence=0.9,
        )

    if outcome.status == NeMoRailStatus.MODIFIED and outcome.rewrite_applied:
        return OutputAssessment(
            flagged=False,
            blocked=False,
            safe_text=outcome.content,
            rewrite_applied=True,
            reasoning="Post-generation safety check applied a safe rewrite.",
            confidence=0.85,
        )

    return OutputAssessment(
        flagged=False,
        reasoning="Post-generation safety check passed.",
        confidence=0.8,
    )


def merge_nemo_into_risk(
    base: RiskAssessment,
    outcome: NeMoRailOutcome,
) -> RiskAssessment:
    """Merge NeMo input/dialog signals into an existing RiskAssessment.

    PolicyEngine retains authority — this only enriches probabilistic evidence.
    """
    if outcome.fail_closed or outcome.status == NeMoRailStatus.INDETERMINATE:
        return base.model_copy(
            update={
                "risk_level": RiskLevel.CRITICAL,
                "confidence": 0.0,
                "reasoning": _join_reasoning(base.reasoning, _FAIL_CLOSED_SUFFIX),
            }
        )

    categories = list(base.categories)
    risk_level = base.risk_level
    injection = base.injection_detected
    disguise = base.disguise_detected
    sensitivity = base.data_sensitivity
    reasoning = base.reasoning

    if outcome.status == NeMoRailStatus.BLOCKED:
        risk_level = _max_risk(risk_level, RiskLevel.CRITICAL)
        injection = True
        disguise = True
        if RiskCategory.PROMPT_INJECTION not in categories:
            categories.append(RiskCategory.PROMPT_INJECTION)
        reasoning = _join_reasoning(reasoning, _BLOCKED_SUFFIX)

    elif outcome.status == NeMoRailStatus.MODIFIED:
        risk_level = _max_risk(risk_level, RiskLevel.MEDIUM)
        if RiskCategory.PII not in categories:
            categories.append(RiskCategory.PII)
        candidate = DataSensitivity.CONFIDENTIAL
        if _SENSITIVITY_RANK[candidate] > _SENSITIVITY_RANK[sensitivity]:
            sensitivity = candidate
        reasoning = _join_reasoning(reasoning, _MODIFIED_SUFFIX)

    return base.model_copy(
        update={
            "risk_level": risk_level,
            "categories": categories or [RiskCategory.NONE],
            "injection_detected": injection,
            "disguise_detected": disguise,
            "data_sensitivity": sensitivity,
            "reasoning": reasoning,
        }
    )


def _max_risk(current: RiskLevel, candidate: RiskLevel) -> RiskLevel:
    if _RISK_RANK[candidate] > _RISK_RANK[current]:
        return candidate
    return current


def _join_reasoning(existing: str, addition: str) -> str:
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing}; {addition}"
