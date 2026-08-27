"""
Policy configuration models (services/policy_engine).

Policies are configuration, not code: rules live in policies/*.yaml. These
pydantic models validate a policy file at load time so that a broken policy
fails loudly at startup instead of surfacing mid-request. The engine only ever
sees validated PolicyRule objects.
"""

from pydantic import BaseModel, Field

from domain.enums import DataSensitivity, PolicyAction, RiskCategory, RiskLevel


class PolicyValidationError(ValueError):
    """Raised when a policy file is missing, malformed, or invalid."""


class PolicyRule(BaseModel):
    id: str
    description: str = ""
    action: PolicyAction
    risk_level: RiskLevel | None = None
    # When set, the rule only matches if the risk level meets or exceeds this
    # minimum. For example, min_risk_level=MEDIUM matches MEDIUM, HIGH, CRITICAL
    # but not LOW.
    min_risk_level: RiskLevel | None = None
    category: RiskCategory | None = None
    disguise_detected: bool | None = None
    injection_detected: bool | None = None
    sensitivity: DataSensitivity | None = None
    # When set, the rule only matches if the conversation trajectory assessment
    # (if any) has this escalate value. Evidence only — the trajectory engine
    # never produces a PolicyDecision.
    trajectory_escalate: bool | None = None
    # When set, the rule only matches if a ClaimEvidenceAssessment was supplied
    # (any claim/evidence verification run over generated claims) AND its
    # verified-ness equals this value (`false` = at least one claim is not
    # fully supported by approved-source evidence). Evidence only — the
    # extraction/verification components never produce a PolicyDecision; see
    # ClaimEvidenceAssessment.all_verified for what "fully supported" means.
    claims_supported: bool | None = None
    # Empty = match any input type (text and image). Non-empty = only match when
    # PolicyEngine.evaluate(..., input_type=...) is one of these values.
    input_types: list[str] = Field(default_factory=list)
    exclude_roles: list[str] = Field(default_factory=list)
    require_roles: list[str] = Field(default_factory=list)
    required_controls: list[str] = Field(default_factory=list)


class PolicyFile(BaseModel):
    version: str = "unknown"
    rules: list[PolicyRule] = Field(default_factory=list)
