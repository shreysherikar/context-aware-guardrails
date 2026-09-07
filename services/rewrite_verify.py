"""Re-classify a sanitized prompt after REWRITE (brief item 5).

Policy still owns the action. This module only reports whether the rewritten
text would be ALLOW if submitted as a fresh request, with no conversation
trajectory. Callers fail closed to REVIEW when verification is false.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.enums import DataSensitivity, PolicyAction, RiskCategory, RiskLevel
from domain.models import GuardrailRequest, RiskAssessment
from services.policy_engine.engine import PolicyEngine
from services.risk_engine.classifier import RiskClassifier


@dataclass(frozen=True)
class RewriteVerification:
    verified: bool
    rationale: str
    follow_up_action: PolicyAction
    follow_up_policy_id: str
    follow_up_risk: RiskAssessment


def verify_rewritten_prompt(
    rewritten: str,
    *,
    classifier: RiskClassifier,
    policy_engine: PolicyEngine,
    role: str,
) -> RewriteVerification:
    """Return whether the sanitized prompt is safe to forward."""
    text = (rewritten or "").strip()
    empty_risk = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        categories=[RiskCategory.NONE],
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
        confidence=1.0,
        reasoning="Sanitized prompt was empty after rewrite.",
    )
    if not text:
        return RewriteVerification(
            verified=False,
            rationale="Sanitized prompt was empty after rewrite.",
            follow_up_action=PolicyAction.REVIEW,
            follow_up_policy_id="REWRITE-VERIFY-EMPTY",
            follow_up_risk=empty_risk,
        )

    risk = classifier.classify(
        GuardrailRequest(prompt=text, conversation_id="rewrite-verify")
    )
    decision = policy_engine.evaluate(risk, role)
    leftover_attack = any(
        category.value
        in {
            "MALWARE",
            "PHISHING",
            "DATA_EXFILTRATION",
            "PROMPT_INJECTION",
            "CYBER_SAFETY",
        }
        for category in risk.categories
    )
    still_blocked = (
        risk.injection_detected
        or risk.disguise_detected
        or leftover_attack
        or decision.action in (PolicyAction.BLOCK, PolicyAction.REVIEW)
    )
    if still_blocked:
        return RewriteVerification(
            verified=False,
            rationale=(
                f"Sanitized prompt still resolved to {decision.action.value} "
                f"({decision.policy_id}). Failing closed to REVIEW."
            ),
            follow_up_action=PolicyAction.REVIEW,
            follow_up_policy_id="REWRITE-VERIFY-FAIL",
            follow_up_risk=risk,
        )
    return RewriteVerification(
        verified=True,
        rationale=(
            "Re-classified sanitized prompt has no remaining block-level risk "
            f"({decision.action.value} / {decision.policy_id})."
        ),
        follow_up_action=decision.action,
        follow_up_policy_id=decision.policy_id,
        follow_up_risk=risk,
    )
