"""Governance domain models for pharma AI agent orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.enums import RiskLevel
from domain.governance_enums import (
    AgentStatus,
    ApprovalStatus,
    DataClassification,
    GovernanceDecision,
    RequestType,
    RewriteStatus,
    SecurityEventCategory,
    SecurityEventSeverity,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AgentRegistryEntry(BaseModel):
    agent_id: str
    name: str
    agent_type: str
    description: str
    owner: str = "pharma-governance"
    version: str = "1.0.0"
    status: AgentStatus = AgentStatus.ACTIVE
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    restricted_actions: list[str] = Field(default_factory=list)
    human_approval_required: list[str] = Field(default_factory=list)
    data_classifications_allowed: list[DataClassification] = Field(default_factory=list)
    tools_allowed: list[str] = Field(default_factory=list)
    computer_use_permissions: list[str] = Field(default_factory=list)
    max_risk_level: RiskLevel = RiskLevel.HIGH
    audit_required: bool = True
    category: str = "general"


class AgentIdentity(BaseModel):
    agent_id: str
    agent_version: str
    request_id: str
    session_id: str
    user_id: str | None = None
    context_role: str | None = None


class AgentActionRequest(BaseModel):
    """Inbound agent action routed through governance."""

    identity: AgentIdentity
    requested_action: str
    requested_resource: str | None = None
    data_classification: DataClassification = DataClassification.INTERNAL
    purpose: str | None = None
    tools_requested: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class GovernedRequest(BaseModel):
    """Unified normalized request — every action passes through governance."""

    request_id: str
    session_id: str
    agent_id: str
    agent_version: str
    user_id: str | None = None
    request_type: RequestType = RequestType.TEXT
    intent: str | None = None
    resource: str | None = None
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    data_classification: DataClassification = DataClassification.INTERNAL
    risk_level: RiskLevel = RiskLevel.LOW
    source: str = "agent"
    timestamp: datetime = Field(default_factory=_utcnow)
    purpose: str | None = None
    tools_requested: list[str] = Field(default_factory=list)

    @classmethod
    def from_action_request(cls, req: AgentActionRequest) -> GovernedRequest:
        request_type = RequestType.TEXT
        action = req.requested_action
        if action.startswith("COMPUTER_"):
            request_type = RequestType.COMPUTER
        elif action in ("SEARCH_LITERATURE", "RUN_ANALYTICS", "RUN_ML_MODEL"):
            request_type = RequestType.TOOL
        elif action.startswith("READ_"):
            request_type = RequestType.DATA
        return cls(
            request_id=req.identity.request_id,
            session_id=req.identity.session_id,
            agent_id=req.identity.agent_id,
            agent_version=req.identity.agent_version,
            user_id=req.identity.user_id,
            request_type=request_type,
            intent=req.purpose,
            resource=req.requested_resource,
            action=action,
            arguments=req.payload,
            data_classification=req.data_classification,
            purpose=req.purpose,
            tools_requested=req.tools_requested,
        )

    def to_action_request(self) -> AgentActionRequest:
        return AgentActionRequest(
            identity=AgentIdentity(
                agent_id=self.agent_id,
                agent_version=self.agent_version,
                request_id=self.request_id,
                session_id=self.session_id,
                user_id=self.user_id,
            ),
            requested_action=self.action,
            requested_resource=self.resource,
            data_classification=self.data_classification,
            purpose=self.purpose or self.intent,
            tools_requested=self.tools_requested,
            payload=self.arguments,
        )


class SafeRewriteResult(BaseModel):
    """Result of safe rewriting middleware — no raw sensitive content in logs."""

    status: RewriteStatus
    original_hash: str
    rewritten_content: str = ""
    detected_threats: list[str] = Field(default_factory=list)
    removed_content: list[str] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    reason: str = ""
    policy_version: str = "1.0.0"
    audit_id: str | None = None
    blocked: bool = False


class ComputerSession(BaseModel):
    """Controlled computer-use session with sandbox boundaries."""

    session_id: str
    agent_id: str
    user_id: str | None = None
    environment_id: str = "sandbox-default"
    start_time: datetime = Field(default_factory=_utcnow)
    expiry_time: datetime
    allowed_domains: list[str] = Field(default_factory=list)
    allowed_apps: list[str] = Field(default_factory=list)
    allowed_directories: list[str] = Field(default_factory=list)
    blocked_directories: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    risk_limit: RiskLevel = RiskLevel.MEDIUM
    approval_policy: str = "high_risk_requires_approval"
    active: bool = True
    current_application: str | None = None
    current_domain: str | None = None
    actions_executed: int = 0
    actions_blocked: int = 0


class ComputerActionResult(BaseModel):
    session_id: str
    request_id: str
    action: str
    target: str | None = None
    decision: GovernanceDecision
    risk_level: RiskLevel = RiskLevel.LOW
    executed: bool = False
    reason: str = ""
    approval_id: str | None = None
    approval_required: bool = False
    log_id: str | None = None
    audit_id: str | None = None
    rewrite_result: SafeRewriteResult | None = None


class ComputerActionLog(BaseModel):
    """Append-only record of every computer-use action attempt."""

    log_id: str
    session_id: str
    agent_id: str
    request_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    action: str
    target: str | None = None
    decision: GovernanceDecision
    risk_level: RiskLevel
    executed: bool = False
    reason: str = ""
    approval_id: str | None = None


class ComputerEnvironment(BaseModel):
    """Predefined sandbox environment configuration."""

    environment_id: str
    name: str
    description: str
    allowed_apps: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    allowed_directories: list[str] = Field(default_factory=list)
    blocked_directories: list[str] = Field(default_factory=list)
    network_restricted: bool = True
    clipboard_restricted: bool = True
    file_transfer_restricted: bool = True
    default_risk_limit: RiskLevel = RiskLevel.MEDIUM
    default_actions: list[str] = Field(default_factory=list)


class GovernancePolicyResult(BaseModel):
    decision: GovernanceDecision
    risk_level: RiskLevel
    policy_id: str
    reasons: list[str] = Field(default_factory=list)
    approval_required: bool = False
    approval_id: str | None = None
    blocked: bool = False
    restricted: bool = False


class GovernanceResponse(BaseModel):
    request_id: str
    agent_id: str
    decision: GovernanceDecision
    risk_level: RiskLevel
    policy_id: str
    reasons: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    approval_required: bool = False
    blocked: bool = False
    audit_id: str | None = None
    security_event_id: str | None = None
    safe_rewrite_applied: bool = False
    rewrite_status: RewriteStatus | None = None
    rewrite_transformations: list[str] = Field(default_factory=list)
    detected_threats: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    approval_request_id: str
    requesting_agent: str
    requested_action: str
    reason: str
    affected_resource: str | None = None
    risk_level: RiskLevel
    timestamp: datetime = Field(default_factory=_utcnow)
    evidence: dict[str, Any] = Field(default_factory=dict)
    approver: str | None = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    request_id: str | None = None
    user_id: str | None = None


class GovernanceAuditRecord(BaseModel):
    timestamp: datetime = Field(default_factory=_utcnow)
    agent_id: str
    user_id: str | None = None
    action: str
    resource: str | None = None
    data_classification: DataClassification
    risk_level: RiskLevel
    policy_decision: GovernanceDecision
    tools_used: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    result: str
    reason: str
    request_id: str | None = None
    session_id: str | None = None
    rewrite_status: str | None = None
    policy_version: str = "1.0.0"


class SecurityEvent(BaseModel):
    event_id: str
    agent_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    severity: SecurityEventSeverity
    category: SecurityEventCategory
    request_id: str | None = None
    description: str
    policy_decision: GovernanceDecision | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class RuntimeStatus(BaseModel):
    active: bool = True
    started_at: datetime
    agents_registered: int
    requests_processed: int
    requests_allowed: int
    requests_blocked: int
    pending_approvals: int
    security_events: int
    audit_entries: int
    active_computer_sessions: int = 0
    emergency_stop_active: bool = False
    rewrites_applied: int = 0


class AgentRegisterRequest(BaseModel):
    agent_id: str
    name: str
    agent_type: str
    description: str
    owner: str = "custom"
    version: str = "1.0.0"
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    restricted_actions: list[str] = Field(default_factory=list)
    human_approval_required: list[str] = Field(default_factory=list)
    data_classifications_allowed: list[DataClassification] = Field(default_factory=list)
    tools_allowed: list[str] = Field(default_factory=list)
    computer_use_permissions: list[str] = Field(default_factory=list)
    max_risk_level: RiskLevel = RiskLevel.MEDIUM
    audit_required: bool = True
    category: str = "custom"
