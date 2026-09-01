"""
Policy engine (policy plane — deterministic).

This is the only module allowed to produce a PolicyDecision. It reads
version-controlled rules from policies/policy.yaml, validates them up front
(see policy_models.py) and does pure rule lookup — no LLM call happens here,
ever. On any error (unmatched risk profile, unexpected evaluation failure) it
fails CLOSED to REVIEW, never open to ALLOW.

The policy path comes from the POLICY_PATH environment variable, falling back
to the repository default, so the deployed configuration is explicit rather
than hardcoded.
"""

import logging
import os
from pathlib import Path

import yaml

from domain.enums import PolicyAction, RiskLevel
from domain.models import (
    ClaimEvidenceAssessment,
    PolicyDecision,
    RiskAssessment,
    TrajectoryAssessment,
)
from services.policy_engine.policy_models import (
    PolicyFile,
    PolicyRule,
    PolicyValidationError,
)

logger = logging.getLogger(__name__)

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "policies" / "policy.yaml"

# Risk level ordering for minimum-threshold comparisons.
_RISK_LEVEL_ORDER = {
    RiskLevel.NONE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


class PolicyEngine:
    def __init__(self, policy_path: Path | None = None):
        self.policy_path = policy_path or Path(os.getenv("POLICY_PATH", str(DEFAULT_POLICY_PATH)))
        self._policy: PolicyFile = self._load_policy()

    def _load_policy(self) -> PolicyFile:
        try:
            with open(self.policy_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except FileNotFoundError as exc:
            raise PolicyValidationError(f"Policy file not found: {self.policy_path}") from exc
        except yaml.YAMLError as exc:
            raise PolicyValidationError(f"Policy file is malformed YAML: {exc}") from exc

        try:
            return PolicyFile.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - pydantic errors are the expected failure mode
            raise PolicyValidationError(
                f"Policy file is invalid ({self.policy_path}): {exc}"
            ) from exc

    def reload(self) -> None:
        self._policy = self._load_policy()

    def evaluate(
        self,
        risk: RiskAssessment,
        user_role: str,
        input_type: str | None = None,
        trajectory: TrajectoryAssessment | None = None,
        claims: ClaimEvidenceAssessment | None = None,
    ) -> PolicyDecision:
        version = self._policy.version
        try:
            for rule in self._policy.rules:
                if self._rule_matches(rule, risk, user_role, input_type, trajectory, claims):
                    return PolicyDecision(
                        action=rule.action,
                        policy_id=rule.id,
                        policy_version=version,
                        reasons=[rule.description or rule.id],
                        required_controls=rule.required_controls,
                    )
            # No rule matched this risk profile at all -> fail closed.
            return PolicyDecision(
                action=PolicyAction.REVIEW,
                policy_id="DEFAULT-FAIL-CLOSED",
                policy_version=version,
                reasons=["No policy rule matched this risk profile; routing to human review."],
            )
        except Exception:  # noqa: BLE001 - fail closed on ANY evaluation error
            logger.exception("Unexpected policy evaluation error; failing closed to REVIEW")
            return PolicyDecision(
                action=PolicyAction.REVIEW,
                policy_id="ERROR-FAIL-CLOSED",
                policy_version=version,
                reasons=["Unexpected policy evaluation error; routing to human review."],
            )

    @staticmethod
    def _rule_matches(
        rule: PolicyRule,
        risk: RiskAssessment,
        user_role: str,
        input_type: str | None = None,
        trajectory: TrajectoryAssessment | None = None,
        claims: ClaimEvidenceAssessment | None = None,
    ) -> bool:
        # Rules with input_types only match when the caller supplies a matching
        # input_type (e.g. "image"). Empty input_types = unrestricted (text + image).
        if rule.input_types:
            if input_type is None or input_type not in rule.input_types:
                return False
        # Trajectory condition: evidence only. A rule requiring escalation never
        # matches when no trajectory assessment is supplied, so existing
        # single-turn callers are unaffected.
        if rule.trajectory_escalate is not None:
            if trajectory is None or trajectory.escalate != rule.trajectory_escalate:
                return False
        # Claim/evidence condition: evidence only. A rule requiring verified
        # claims never matches when no claim/evidence assessment is supplied,
        # so callers without a verification stage are unaffected. Verified-ness
        # comes from the aggregate's conservative derived view; this engine adds
        # no claim logic of its own.
        if rule.claims_supported is not None:
            if claims is None or claims.all_verified != rule.claims_supported:
                return False
        if rule.risk_level is not None and rule.risk_level != risk.risk_level:
            return False
        if rule.min_risk_level is not None:
            if _RISK_LEVEL_ORDER.get(risk.risk_level, 0) < _RISK_LEVEL_ORDER.get(
                rule.min_risk_level, 0
            ):
                return False
        if rule.category is not None and rule.category not in risk.categories:
            return False
        # Disguise and injection are separate signals: either can be present
        # without the other, so each has its own condition.
        if rule.disguise_detected is not None and rule.disguise_detected != risk.disguise_detected:
            return False
        if (
            rule.injection_detected is not None
            and rule.injection_detected != risk.injection_detected
        ):
            return False
        if rule.sensitivity is not None and rule.sensitivity != risk.data_sensitivity:
            return False
        if user_role in rule.exclude_roles:
            return False
        if rule.require_roles and user_role not in rule.require_roles:
            return False
        return True
