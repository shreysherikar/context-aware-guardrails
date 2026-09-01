"""Governance API routes — centralized control plane endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from domain.enums import RiskLevel
from domain.governance_enums import DataClassification, RequestType
from domain.governance_models import (
    AgentActionRequest,
    AgentIdentity,
    AgentRegisterRequest,
    AgentRegistryEntry,
    ApprovalRequest,
    ComputerActionLog,
    ComputerActionResult,
    ComputerEnvironment,
    ComputerSession,
    GovernedRequest,
    GovernanceAuditRecord,
    GovernanceResponse,
    RuntimeStatus,
    SafeRewriteResult,
    SecurityEvent,
)
from services.governance.computer_use.environments import list_environments
from services.governance.runtime import get_runtime
from services.gxp.models import GxpReviewResult
from services.gxp.reviewer import list_gxp_frameworks, review_text

router = APIRouter(tags=["governance"])


class AgentRequestBody(BaseModel):
    agent_id: str
    agent_version: str = "1.0.0"
    request_id: str
    session_id: str
    user_id: str | None = None
    context_role: str | None = None
    requested_action: str
    requested_resource: str | None = None
    data_classification: DataClassification = DataClassification.INTERNAL
    purpose: str | None = None
    tools_requested: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)


class GovernedRequestBody(BaseModel):
    request_id: str
    session_id: str
    agent_id: str
    agent_version: str = "1.0.0"
    user_id: str | None = None
    request_type: RequestType = RequestType.TEXT
    intent: str | None = None
    resource: str | None = None
    action: str
    arguments: dict = Field(default_factory=dict)
    data_classification: DataClassification = DataClassification.INTERNAL
    purpose: str | None = None
    tools_requested: list[str] = Field(default_factory=list)


class PolicyEvaluateBody(BaseModel):
    agent_id: str
    requested_action: str
    data_classification: DataClassification = DataClassification.INTERNAL
    purpose: str | None = None
    tools_requested: list[str] = Field(default_factory=list)
    request_id: str = "policy-eval"
    session_id: str = "policy-eval"
    payload: dict = Field(default_factory=dict)


class RewriteBody(BaseModel):
    agent_id: str
    request_id: str = "rewrite-eval"
    session_id: str = "rewrite-eval"
    text: str
    data_classification: DataClassification = DataClassification.INTERNAL
    purpose: str | None = None
    source: str = "agent"
    untrusted_document: bool = False


class ApprovalActionBody(BaseModel):
    approver: str


class ComputerSessionBody(BaseModel):
    agent_id: str
    user_id: str | None = None
    environment_id: str = "sandbox-default"
    allowed_domains: list[str] = Field(default_factory=list)
    allowed_apps: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    risk_limit: RiskLevel = RiskLevel.MEDIUM
    ttl_minutes: int = 30


class ComputerActionBody(BaseModel):
    request_id: str
    action: str
    target: str | None = None
    arguments: dict = Field(default_factory=dict)
    purpose: str | None = None
    approval_id: str | None = None


class EmergencyStopBody(BaseModel):
    by: str = "admin"
    reason: str = "EMERGENCY_STOP"


class GxpReviewBody(BaseModel):
    text: str
    document_type: str | None = None


def _to_action_request(body: AgentRequestBody) -> AgentActionRequest:
    return AgentActionRequest(
        identity=AgentIdentity(
            agent_id=body.agent_id,
            agent_version=body.agent_version,
            request_id=body.request_id,
            session_id=body.session_id,
            user_id=body.user_id,
            context_role=body.context_role,
        ),
        requested_action=body.requested_action,
        requested_resource=body.requested_resource,
        data_classification=body.data_classification,
        purpose=body.purpose,
        tools_requested=body.tools_requested,
        payload=body.payload,
    )


def _to_governed(body: GovernedRequestBody) -> GovernedRequest:
    return GovernedRequest(
        request_id=body.request_id,
        session_id=body.session_id,
        agent_id=body.agent_id,
        agent_version=body.agent_version,
        user_id=body.user_id,
        request_type=body.request_type,
        intent=body.intent,
        resource=body.resource,
        action=body.action,
        arguments=body.arguments,
        data_classification=body.data_classification,
        purpose=body.purpose,
        tools_requested=body.tools_requested,
    )


# --- Agent Registry ---

@router.post("/agents/register", response_model=AgentRegistryEntry)
def register_agent(body: AgentRegisterRequest) -> AgentRegistryEntry:
    runtime = get_runtime()
    try:
        return runtime.register_agent(body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/agents", response_model=list[AgentRegistryEntry])
def list_agents() -> list[AgentRegistryEntry]:
    return get_runtime().list_agents()


@router.get("/agents/{agent_id}", response_model=AgentRegistryEntry)
def get_agent(agent_id: str) -> AgentRegistryEntry:
    agent = get_runtime().get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


# --- Unified Requests ---

@router.post("/requests", response_model=GovernanceResponse)
def submit_request(body: GovernedRequestBody) -> GovernanceResponse:
    return get_runtime().process_governed(_to_governed(body))


@router.post("/requests/evaluate", response_model=GovernanceResponse)
def evaluate_request(body: GovernedRequestBody) -> GovernanceResponse:
    return get_runtime().process_governed(_to_governed(body))


@router.post("/agents/{agent_id}/request", response_model=GovernanceResponse)
def agent_request(agent_id: str, body: AgentRequestBody) -> GovernanceResponse:
    if body.agent_id != agent_id:
        raise HTTPException(status_code=400, detail="agent_id mismatch")
    return get_runtime().process_request(_to_action_request(body))


@router.post("/policy/evaluate", response_model=GovernanceResponse)
def policy_evaluate(body: PolicyEvaluateBody) -> GovernanceResponse:
    agent = get_runtime().get_agent(body.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    req = AgentActionRequest(
        identity=AgentIdentity(
            agent_id=body.agent_id,
            agent_version=agent.version,
            request_id=body.request_id,
            session_id=body.session_id,
        ),
        requested_action=body.requested_action,
        data_classification=body.data_classification,
        purpose=body.purpose,
        tools_requested=body.tools_requested,
        payload=body.payload,
    )
    return get_runtime().process_request(req)


# --- Safe Rewriting ---

@router.post("/rewrite", response_model=SafeRewriteResult)
def rewrite_content(body: RewriteBody) -> SafeRewriteResult:
    governed = GovernedRequest(
        request_id=body.request_id,
        session_id=body.session_id,
        agent_id=body.agent_id,
        agent_version="1.0.0",
        action="REWRITE",
        arguments={
            "text": body.text,
            "source": body.source,
            "untrusted_document": body.untrusted_document,
        },
        data_classification=body.data_classification,
        purpose=body.purpose,
    )
    return get_runtime().rewrite(governed)


@router.post("/rewrite/evaluate", response_model=GovernanceResponse)
def rewrite_and_evaluate(body: RewriteBody) -> GovernanceResponse:
    governed = GovernedRequest(
        request_id=body.request_id,
        session_id=body.session_id,
        agent_id=body.agent_id,
        agent_version="1.0.0",
        action="CREATE_DRAFT",
        arguments={
            "text": body.text,
            "source": body.source,
            "untrusted_document": body.untrusted_document,
        },
        data_classification=body.data_classification,
        purpose=body.purpose,
    )
    return get_runtime().process_governed(governed)


@router.get("/rewrite/recent")
def recent_rewrites(limit: int = 20) -> list[dict]:
    return get_runtime().list_recent_rewrites(limit)


# --- Approvals ---

@router.get("/approval", response_model=list[ApprovalRequest])
@router.get("/approvals", response_model=list[ApprovalRequest])
def list_approvals() -> list[ApprovalRequest]:
    return get_runtime().list_pending_approvals()


@router.post("/approval/{approval_id}/approve", response_model=ApprovalRequest)
@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRequest)
def approve_request(approval_id: str, body: ApprovalActionBody) -> ApprovalRequest:
    result = get_runtime().approve(approval_id, body.approver)
    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found or not pending")
    return result


@router.post("/approval/{approval_id}/reject", response_model=ApprovalRequest)
@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRequest)
def reject_request(approval_id: str, body: ApprovalActionBody) -> ApprovalRequest:
    result = get_runtime().reject(approval_id, body.approver)
    if result is None:
        raise HTTPException(status_code=404, detail="Approval not found or not pending")
    return result


# --- Computer Use ---

@router.get("/computer/environments", response_model=list[ComputerEnvironment])
def list_computer_environments() -> list[ComputerEnvironment]:
    return list_environments()


@router.post("/computer/sessions", response_model=ComputerSession)
def create_computer_session(body: ComputerSessionBody) -> ComputerSession:
    runtime = get_runtime()
    agent = runtime.get_agent(body.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return runtime.computer_engine.create_session(
        agent,
        user_id=body.user_id,
        environment_id=body.environment_id,
        allowed_domains=body.allowed_domains or None,
        allowed_apps=body.allowed_apps or None,
        allowed_actions=body.allowed_actions or None,
        risk_limit=body.risk_limit,
        ttl_minutes=body.ttl_minutes,
    )


@router.get("/computer/sessions", response_model=list[ComputerSession])
def list_computer_sessions() -> list[ComputerSession]:
    return get_runtime().computer_engine.list_active_sessions()


@router.get("/computer/sessions/{session_id}", response_model=ComputerSession)
def get_computer_session(session_id: str) -> ComputerSession:
    session = get_runtime().computer_engine.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session


@router.get("/computer/sessions/{session_id}/actions", response_model=list[ComputerActionLog])
def list_session_actions(session_id: str, limit: int = 50) -> list[ComputerActionLog]:
    runtime = get_runtime()
    session = runtime.computer_engine.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return runtime.computer_engine.list_action_log(session_id=session_id, limit=limit)


@router.get("/computer/actions", response_model=list[ComputerActionLog])
def list_recent_computer_actions(limit: int = 50) -> list[ComputerActionLog]:
    return get_runtime().computer_engine.list_action_log(limit=limit)


@router.post("/computer/sessions/{session_id}/actions", response_model=ComputerActionResult)
def computer_action(session_id: str, body: ComputerActionBody) -> ComputerActionResult:
    runtime = get_runtime()
    session = runtime.computer_engine.session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    governed = GovernedRequest(
        request_id=body.request_id,
        session_id=session_id,
        agent_id=session.agent_id,
        agent_version="1.0.0",
        request_type=RequestType.COMPUTER,
        action=body.action,
        resource=body.target,
        arguments=body.arguments,
        purpose=body.purpose,
    )
    return runtime.execute_computer_action(session_id, governed, approval_id=body.approval_id)


@router.post("/computer/sessions/{session_id}/stop", response_model=ComputerSession)
def stop_computer_session(session_id: str) -> ComputerSession:
    result = get_runtime().computer_engine.stop_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


# --- GxP Review ---

@router.get("/gxp/frameworks")
def get_gxp_frameworks() -> list[dict[str, str]]:
    return list_gxp_frameworks()


@router.post("/gxp/review", response_model=GxpReviewResult)
def gxp_review(body: GxpReviewBody) -> GxpReviewResult:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    return review_text(body.text)


# --- Emergency Kill Switch ---

@router.post("/system/emergency-stop")
def activate_emergency_stop(body: EmergencyStopBody) -> dict:
    get_runtime().activate_emergency_stop(by=body.by, reason=body.reason)
    return {"status": "EMERGENCY_STOP", "active": True, "reason": body.reason}


@router.post("/system/emergency-stop/deactivate")
def deactivate_emergency_stop(body: EmergencyStopBody) -> dict:
    get_runtime().deactivate_emergency_stop(by=body.by)
    return {"status": "active", "emergency_stop": False}


# --- Audit & Security ---

@router.get("/audit", response_model=list[GovernanceAuditRecord])
def get_audit(limit: int = 50) -> list[GovernanceAuditRecord]:
    return get_runtime().list_audit(limit)


@router.get("/security/events", response_model=list[SecurityEvent])
def get_security_events(limit: int = 50) -> list[SecurityEvent]:
    return get_runtime().list_security_events(limit)


@router.get("/system/status", response_model=RuntimeStatus)
def system_status() -> RuntimeStatus:
    return get_runtime().get_status()
