"""Bridge multimodal classifier decisions into PolicyEngine outcomes for images."""

from __future__ import annotations

from domain.enums import PolicyAction
from domain.models import OpticalAssessment, PolicyDecision, RiskAssessment
from services.multimodal.classifier import assess_multimodal_content

_INJECTION_BLOCK_POLICIES = frozenset({"INJECTION-001", "INJECTION-002", "OPT-INJECTION-001"})


def apply_multimodal_image_policy(
    optical: OpticalAssessment,
    risk: RiskAssessment,
    decision: PolicyDecision,
) -> PolicyDecision:
    """Align policy decision with multimodal assessment for image intake."""
    _ = risk  # reserved for future role/sensitivity overrides
    mm = assess_multimodal_content(optical.ocr_text or "", source="image")

    if mm.decision == "BLOCK":
        if decision.action != PolicyAction.BLOCK:
            return decision.model_copy(
                update={
                    "action": PolicyAction.BLOCK,
                    "policy_id": "MULTIMODAL-BLOCK",
                    "reasons": mm.reasons[:3]
                    or ["Multimodal threat blocked — visual content is not authorization"],
                }
            )
        return decision

    if mm.decision == "REWRITE":
        if decision.action == PolicyAction.BLOCK and decision.policy_id in _INJECTION_BLOCK_POLICIES:
            return decision.model_copy(
                update={
                    "action": PolicyAction.REWRITE,
                    "policy_id": "OPT-MULTIMODAL-REWRITE",
                    "reasons": [
                        "Multimodal safe rewrite — preserve factual content, remove untrusted instructions"
                    ],
                }
            )
        if decision.action == PolicyAction.ALLOW and (
            mm.authority_spoofing or mm.injection_detected
        ):
            return decision.model_copy(
                update={
                    "action": PolicyAction.REWRITE,
                    "policy_id": "OPT-AUTHORITY-001"
                    if mm.authority_spoofing
                    else "OPT-MULTIMODAL-REWRITE",
                    "reasons": ["Untrusted multimodal content requires sanitization"],
                }
            )

    return decision
