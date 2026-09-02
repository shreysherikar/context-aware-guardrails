"""Always-active governance runtime — persistent agent governance layer."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from domain.governance_enums import (
    GovernanceDecision,
    RewriteStatus,
    SecurityEventCategory,
)
from domain.governance_models import (
    AgentActionRequest,
    AgentRegisterRequest,
    AgentRegistryEntry,
    ComputerActionResult,
    GovernanceAuditRecord,
    GovernanceResponse,
    GovernedRequest,
    RuntimeStatus,
    SafeRewriteResult,
)
from services.governance.anti_escalation import AntiEscalationGuard
from services.governance.approval import ApprovalStore
from services.governance.audit import GovernanceAuditStore
from services.governance.computer_use.engine import ComputerUseEngine
from services.governance.data_access import DataAccessController
from services.governance.identity import IdentityLayer
from services.governance.kill_switch import KillSwitch, get_kill_switch
from services.governance.permissions import PermissionEngine
from services.governance.policy import GovernancePolicyEngine
from services.governance.registry import AgentRegistry
from services.governance.risk import GovernanceRiskEngine
from services.governance.safe_rewrite import IntegratedSafeRewrite, SafeRewritePipeline
from services.governance.security_events import SecurityEventStore
from services.governance.tool_gateway import ToolGateway, build_default_tool_gateway

logger = logging.getLogger(__name__)


class GovernanceRuntime:
    """
    Persistent governance runtime — remains active independently of agent sessions.
    Full pipeline:
    IDENTITY → KILL SWITCH → ANTI-ESCALATION → POLICY(pre) → SAFE REWRITE →
    POLICY(post) → APPROVAL → AUDIT → TOOL/COMPUTER GATEWAY
    """

    def __init__(
        self,
        *,
        registry: AgentRegistry | None = None,
        audit: GovernanceAuditStore | None = None,
        approvals: ApprovalStore | None = None,
        events: SecurityEventStore | None = None,
        safe_rewrite: SafeRewritePipeline | None = None,
        computer_engine: ComputerUseEngine | None = None,
        kill_switch: KillSwitch | None = None,
        policy_enabled: bool = True,
        audit_enabled: bool = True,
        rewrite_enabled: bool = True,
    ) -> None:
        self._registry = registry or AgentRegistry()
        self._audit = audit or GovernanceAuditStore()
        self._approvals = approvals or ApprovalStore()
        self._events = events or SecurityEventStore()
        self._safe_rewrite = safe_rewrite or IntegratedSafeRewrite()
        self._kill_switch = kill_switch or get_kill_switch()
        self._computer = computer_engine or ComputerUseEngine(
            kill_switch=self._kill_switch,
            approvals=self._approvals,
            events=self._events,
        )
        self._tool_gateway = build_default_tool_gateway(self._computer)
        self._identity = IdentityLayer(self._registry, self._events)
        self._anti_escalation = AntiEscalationGuard(self._events)
        self._policy = GovernancePolicyEngine()
        self._permissions = PermissionEngine()
        self._risk = GovernanceRiskEngine()
        self._data_access = DataAccessController()
        self._policy_enabled = policy_enabled
        self._audit_enabled = audit_enabled
        self._rewrite_enabled = rewrite_enabled
        self._active = True
        self._started_at = datetime.now(UTC)
        self._stats = {
            "processed": 0,
            "allowed": 0,
            "blocked": 0,
            "rewrites": 0,
        }
        self._recent_rewrites: list[dict] = []
        self._rate_window: dict[str, list[float]] = {}
        self._rate_limit = 100

    @property
    def active(self) -> bool:
        return self._active

    @property
    def tool_gateway(self) -> ToolGateway:
        return self._tool_gateway

    @property
    def computer_engine(self) -> ComputerUseEngine:
        return self._computer

    @property
    def kill_switch(self) -> KillSwitch:
        return self._kill_switch

    def register_agent(self, entry: AgentRegisterRequest) -> AgentRegistryEntry:
        return self._registry.register(entry)

    def get_agent(self, agent_id: str) -> AgentRegistryEntry | None:
        return self._registry.get(agent_id)

    def list_agents(self) -> list[AgentRegistryEntry]:
        return self._registry.list_all()

    def process_governed(self, governed: GovernedRequest) -> GovernanceResponse:
        """Process a unified GovernedRequest through the full pipeline."""
        return self._pipeline(governed)

    def process_request(self, request: AgentActionRequest) -> GovernanceResponse:
        governed = GovernedRequest.from_action_request(request)
        return self._pipeline(governed)

    def rewrite(self, governed: GovernedRequest) -> SafeRewriteResult:
        agent = self._registry.get(governed.agent_id)
        _, result = self._safe_rewrite.rewrite_governed(governed, agent)
        return result

    def invoke_tool(
        self,
        governed: GovernedRequest,
        *,
        approval_id: str | None = None,
    ) -> dict:
        agent = self._registry.get(governed.agent_id)
        if agent is None:
            return {"error": "agent_not_found"}
        response = self._pipeline(governed)
        if approval_id and not self._approvals.is_valid(approval_id):
            return {"error": "invalid_approval", "request_id": governed.request_id}
        return self._tool_gateway.invoke(governed, agent, response)

    def _pipeline(self, governed: GovernedRequest) -> GovernanceResponse:
        self._stats["processed"] += 1
        req_id = governed.request_id
        agent_id = governed.agent_id
        request = governed.to_action_request()

        if not self._policy_enabled:
            return self._fail_closed(request, "Policy engine unavailable")

        agent_entry = self._registry.get(agent_id)
        if agent_entry and agent_entry.audit_required and self._audit_enabled:
            if not self._audit.available:
                return self._fail_closed(request, "Audit logging unavailable")

        # Kill switch — fail closed
        ks_ok, ks_reason = self._kill_switch.check()
        if not ks_ok:
            self._stats["blocked"] += 1
            return GovernanceResponse(
                request_id=req_id,
                agent_id=agent_id,
                decision=GovernanceDecision.BLOCK,
                risk_level=self._risk.classify(governed.action, governed.data_classification),
                policy_id="GOV-EMERGENCY-STOP",
                reasons=[ks_reason or "EMERGENCY_STOP"],
                blocked=True,
            )

        if not self._check_rate_limit(agent_id):
            event = self._events.record(
                agent_id=agent_id,
                category=SecurityEventCategory.EXCESSIVE_TOOL_CALLS,
                description="Rate limit exceeded",
                request_id=req_id,
                policy_decision=GovernanceDecision.BLOCK,
            )
            self._stats["blocked"] += 1
            return GovernanceResponse(
                request_id=req_id,
                agent_id=agent_id,
                decision=GovernanceDecision.BLOCK,
                risk_level=self._risk.classify(governed.action, governed.data_classification),
                policy_id="GOV-RATE-LIMIT",
                reasons=["Rate limit exceeded"],
                blocked=True,
                security_event_id=event.event_id,
            )

        # 1. Identity
        ok, err, id_event = self._identity.verify(request.identity)
        if not ok:
            self._stats["blocked"] += 1
            return GovernanceResponse(
                request_id=req_id,
                agent_id=agent_id,
                decision=GovernanceDecision.BLOCK
                if id_event
                else GovernanceDecision.REVIEW_REQUIRED,
                risk_level=self._risk.classify(governed.action, governed.data_classification),
                policy_id="GOV-IDENTITY-FAIL",
                reasons=[err or "Identity verification failed"],
                blocked=True,
                security_event_id=id_event.event_id if id_event else None,
            )

        # 2. Anti-escalation
        esc_ok, esc_event = self._anti_escalation.check(request)
        if not esc_ok:
            self._stats["blocked"] += 1
            resp = self._build_response(
                request,
                GovernanceDecision.BLOCK,
                "GOV-ESCALATION-BLOCK",
                ["Privilege escalation blocked"],
                blocked=True,
            )
            resp.security_event_id = esc_event.event_id if esc_event else None
            return self._audit_and_return(request, agent_entry, resp)

        if agent_entry is None:
            return self._fail_closed(request, "Agent not found", GovernanceDecision.BLOCK)

        # 3. Pre-rewrite policy evaluation
        pre_policy = self._policy.evaluate(agent_entry, request)

        # 4. Safe rewrite (mandatory middleware)
        rewrite_result: SafeRewriteResult | None = None
        if self._rewrite_enabled:
            governed, rewrite_result = self._safe_rewrite.rewrite_governed(governed, agent_entry)
            request = governed.to_action_request()

            if rewrite_result.blocked:
                self._stats["blocked"] += 1
                event = self._events.record(
                    agent_id=agent_id,
                    category=SecurityEventCategory.PROMPT_INJECTION,
                    description="Safe rewrite blocked request",
                    request_id=req_id,
                    policy_decision=GovernanceDecision.BLOCK,
                    evidence={"threats": rewrite_result.detected_threats},
                )
                resp = GovernanceResponse(
                    request_id=req_id,
                    agent_id=agent_id,
                    decision=GovernanceDecision.BLOCK,
                    risk_level=self._risk.classify(governed.action, governed.data_classification),
                    policy_id="GOV-REWRITE-BLOCK",
                    reasons=[rewrite_result.reason or "Safe rewrite blocked"],
                    blocked=True,
                    safe_rewrite_applied=True,
                    rewrite_status=rewrite_result.status,
                    rewrite_transformations=rewrite_result.transformations,
                    detected_threats=rewrite_result.detected_threats,
                    security_event_id=event.event_id,
                )
                self._record_rewrite(governed, rewrite_result, resp.decision)
                return self._audit_and_return(request, agent_entry, resp, rewrite_result)

            if rewrite_result.status == RewriteStatus.REWRITTEN:
                self._stats["rewrites"] += 1

            if rewrite_result.status == RewriteStatus.REVIEW and not rewrite_result.transformations:
                self._stats["blocked"] += 1
                resp = GovernanceResponse(
                    request_id=req_id,
                    agent_id=agent_id,
                    decision=GovernanceDecision.REVIEW_REQUIRED,
                    risk_level=self._risk.classify(governed.action, governed.data_classification),
                    policy_id="GOV-REWRITE-REVIEW",
                    reasons=[rewrite_result.reason or "Rewrite requires review"],
                    blocked=True,
                    safe_rewrite_applied=True,
                    rewrite_status=rewrite_result.status,
                    detected_threats=rewrite_result.detected_threats,
                )
                self._record_rewrite(governed, rewrite_result, resp.decision)
                return self._audit_and_return(request, agent_entry, resp, rewrite_result)

        # 5. Post-rewrite policy re-evaluation (mandatory)
        policy_result = self._policy.evaluate(agent_entry, request)

        # If pre-policy said REWRITE, ensure post-rewrite allows
        if pre_policy.decision == GovernanceDecision.REWRITE:
            if policy_result.decision == GovernanceDecision.BLOCK:
                self._stats["blocked"] += 1

        approval_id = None
        if policy_result.approval_required:
            approval = self._approvals.create(
                requesting_agent=agent_id,
                requested_action=governed.action,
                reason="; ".join(policy_result.reasons),
                risk_level=policy_result.risk_level,
                affected_resource=governed.resource,
                request_id=req_id,
                user_id=governed.user_id,
            )
            approval_id = approval.approval_request_id

        resp = GovernanceResponse(
            request_id=req_id,
            agent_id=agent_id,
            decision=policy_result.decision,
            risk_level=policy_result.risk_level,
            policy_id=policy_result.policy_id,
            reasons=policy_result.reasons,
            approval_id=approval_id,
            approval_required=policy_result.approval_required,
            blocked=policy_result.blocked,
            safe_rewrite_applied=rewrite_result is not None
            and rewrite_result.status != RewriteStatus.SAFE,
            rewrite_status=rewrite_result.status if rewrite_result else None,
            rewrite_transformations=rewrite_result.transformations if rewrite_result else [],
            detected_threats=rewrite_result.detected_threats if rewrite_result else [],
        )

        if policy_result.decision == GovernanceDecision.ALLOW:
            self._stats["allowed"] += 1
        elif policy_result.blocked:
            self._stats["blocked"] += 1
            if policy_result.decision == GovernanceDecision.BLOCK:
                self._events.record(
                    agent_id=agent_id,
                    category=SecurityEventCategory.PERMISSION_VIOLATION,
                    description=f"Blocked: {governed.action}",
                    request_id=req_id,
                    policy_decision=GovernanceDecision.BLOCK,
                )

        if rewrite_result:
            self._record_rewrite(governed, rewrite_result, resp.decision)

        return self._audit_and_return(request, agent_entry, resp, rewrite_result)

    def execute_computer_action(
        self,
        session_id: str,
        governed: GovernedRequest,
        *,
        approval_id: str | None = None,
    ) -> ComputerActionResult:
        agent = self._registry.get(governed.agent_id)
        if agent is None:
            return ComputerActionResult(
                session_id=session_id,
                request_id=governed.request_id,
                action=governed.action,
                decision=GovernanceDecision.BLOCK,
                reason="Agent not found",
            )
        _, rewrite_result = self._safe_rewrite.rewrite_governed(governed, agent)
        return self._computer.execute_action(
            session_id,
            governed,
            agent,
            rewrite_result=rewrite_result,
            approval_id=approval_id,
        )

    def activate_emergency_stop(self, *, by: str = "admin", reason: str = "EMERGENCY_STOP") -> None:
        self._kill_switch.activate(by=by, reason=reason)
        self._computer.session_store.stop_all()

    def deactivate_emergency_stop(self, *, by: str = "admin") -> None:
        self._kill_switch.deactivate(by=by)

    def list_recent_rewrites(self, limit: int = 20) -> list[dict]:
        return self._recent_rewrites[-limit:]

    def get_status(self) -> RuntimeStatus:
        return RuntimeStatus(
            active=self._active,
            started_at=self._started_at,
            agents_registered=self._registry.count(),
            requests_processed=self._stats["processed"],
            requests_allowed=self._stats["allowed"],
            requests_blocked=self._stats["blocked"],
            pending_approvals=self._approvals.count_pending(),
            security_events=self._events.count(),
            audit_entries=self._audit.count(),
            active_computer_sessions=self._computer.session_store.count_active(),
            emergency_stop_active=self._kill_switch.is_active,
            rewrites_applied=self._stats["rewrites"],
        )

    def list_audit(self, limit: int = 50):
        return self._audit.list_recent(limit)

    def list_security_events(self, limit: int = 50):
        return self._events.list_recent(limit)

    def list_pending_approvals(self):
        return self._approvals.list_pending()

    def approve(self, approval_id: str, approver: str):
        return self._approvals.approve(approval_id, approver)

    def reject(self, approval_id: str, approver: str):
        return self._approvals.reject(approval_id, approver)

    def _record_rewrite(
        self,
        governed: GovernedRequest,
        result: SafeRewriteResult,
        decision: GovernanceDecision,
    ) -> None:
        self._recent_rewrites.append(
            {
                "request_id": governed.request_id,
                "agent_id": governed.agent_id,
                "status": result.status.value,
                "transformations": result.transformations,
                "threats": result.detected_threats,
                "decision": decision.value,
                "confidence": result.confidence,
                "original_hash": result.original_hash,
            }
        )
        if len(self._recent_rewrites) > 200:
            self._recent_rewrites = self._recent_rewrites[-200:]

    def _audit_and_return(
        self,
        request: AgentActionRequest,
        agent: AgentRegistryEntry | None,
        response: GovernanceResponse,
        rewrite_result: SafeRewriteResult | None = None,
    ) -> GovernanceResponse:
        if agent and agent.audit_required and self._audit_enabled:
            try:
                record = GovernanceAuditRecord(
                    agent_id=request.identity.agent_id,
                    user_id=request.identity.user_id,
                    action=request.requested_action,
                    resource=request.requested_resource,
                    data_classification=request.data_classification,
                    risk_level=response.risk_level,
                    policy_decision=response.decision,
                    tools_used=request.tools_requested,
                    approval_id=response.approval_id,
                    result="blocked" if response.blocked else response.decision.value,
                    reason="; ".join(response.reasons),
                    request_id=request.identity.request_id,
                    session_id=request.identity.session_id,
                    rewrite_status=rewrite_result.status.value if rewrite_result else None,
                )
                audit_id = self._audit.append(record)
                response.audit_id = audit_id
            except Exception:
                logger.exception("Audit logging failed — fail-closed")
                self._events.record(
                    agent_id=request.identity.agent_id,
                    category=SecurityEventCategory.AUDIT_FAILURE,
                    description="Audit append failed",
                    request_id=request.identity.request_id,
                    policy_decision=GovernanceDecision.REVIEW_REQUIRED,
                )
                if response.decision == GovernanceDecision.ALLOW:
                    response.decision = GovernanceDecision.REVIEW_REQUIRED
                    response.blocked = True
                    response.reasons = ["Audit logging failed — action not executed"]
        return response

    def _fail_closed(
        self,
        request: AgentActionRequest,
        reason: str,
        decision: GovernanceDecision = GovernanceDecision.REVIEW_REQUIRED,
    ) -> GovernanceResponse:
        self._stats["blocked"] += 1
        return GovernanceResponse(
            request_id=request.identity.request_id,
            agent_id=request.identity.agent_id,
            decision=decision,
            risk_level=self._risk.classify(request.requested_action, request.data_classification),
            policy_id="GOV-FAIL-CLOSED",
            reasons=[reason],
            blocked=True,
        )

    def _build_response(
        self,
        request: AgentActionRequest,
        decision: GovernanceDecision,
        policy_id: str,
        reasons: list[str],
        *,
        blocked: bool = False,
    ) -> GovernanceResponse:
        return GovernanceResponse(
            request_id=request.identity.request_id,
            agent_id=request.identity.agent_id,
            decision=decision,
            risk_level=self._risk.classify(request.requested_action, request.data_classification),
            policy_id=policy_id,
            reasons=reasons,
            blocked=blocked,
        )

    def _check_rate_limit(self, agent_id: str) -> bool:
        import time

        now = time.time()
        window = self._rate_window.setdefault(agent_id, [])
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= self._rate_limit:
            return False
        window.append(now)
        return True


_runtime: GovernanceRuntime | None = None


def get_runtime() -> GovernanceRuntime:
    global _runtime
    if _runtime is None:
        _runtime = GovernanceRuntime()
        logger.info(
            "Governance runtime started with %d registered agents",
            _runtime._registry.count(),
        )
    return _runtime
