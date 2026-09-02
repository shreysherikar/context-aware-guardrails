"""Governance policy engine — deterministic action authorization."""

from __future__ import annotations

from domain.enums import RiskLevel
from domain.governance_enums import GovernanceDecision
from domain.governance_models import AgentActionRequest, AgentRegistryEntry, GovernancePolicyResult
from services.cyber_safety.darkweb import assess_darkweb_content, extract_text_for_assessment
from services.governance.data_access import DataAccessController
from services.governance.permissions import PermissionEngine
from services.governance.risk import RISK_ORDER, GovernanceRiskEngine


class GovernancePolicyEngine:
    """
    Every agent action passes through:
    PERMISSION → DATA ACCESS → PURPOSE → RISK → DECISION
    """

    def __init__(self) -> None:
        self._permissions = PermissionEngine()
        self._data_access = DataAccessController()
        self._risk = GovernanceRiskEngine()

    def evaluate(
        self,
        agent: AgentRegistryEntry,
        request: AgentActionRequest,
    ) -> GovernancePolicyResult:
        action = request.requested_action
        agent_perms = set(agent.permissions)

        # DARKWEB_ACCESS_PREVENTION — evaluate textual intent before permissions
        assessable = extract_text_for_assessment(
            request.payload,
            purpose=request.purpose or "",
            action=action,
        )
        if assessable.strip():
            darkweb = assess_darkweb_content(
                assessable,
                is_computer_action=action.startswith("COMPUTER_"),
                is_tool_request=bool(request.tools_requested),
            )
            if darkweb.decision == "BLOCK":
                return GovernancePolicyResult(
                    decision=GovernanceDecision.BLOCK,
                    risk_level=darkweb.risk_level,
                    policy_id="DARKWEB_ACCESS_PREVENTION",
                    reasons=darkweb.reasons or ["Dark-web access prevention policy"],
                    blocked=True,
                )
            if darkweb.decision == "REWRITE":
                return GovernancePolicyResult(
                    decision=GovernanceDecision.REWRITE,
                    risk_level=darkweb.risk_level,
                    policy_id="DARKWEB_ACCESS_PREVENTION",
                    reasons=darkweb.reasons or ["Content requires safe rewrite"],
                )

        # Restricted actions are never implicitly granted
        if self._permissions.is_restricted_action(action):
            if action not in agent_perms:
                if self._permissions.requires_human_approval(
                    action, set(agent.human_approval_required)
                ):
                    risk = self._risk.classify(
                        action, request.data_classification, is_restricted=True
                    )
                    return GovernancePolicyResult(
                        decision=GovernanceDecision.HUMAN_APPROVAL_REQUIRED,
                        risk_level=risk,
                        policy_id="GOV-RESTRICTED-APPROVAL",
                        reasons=[f"Restricted action {action} requires human approval"],
                        approval_required=True,
                    )
                return GovernancePolicyResult(
                    decision=GovernanceDecision.BLOCK,
                    risk_level=RiskLevel.HIGH,
                    policy_id="GOV-RESTRICTED-DENIED",
                    reasons=[f"Restricted action {action} not permitted for agent"],
                    blocked=True,
                )

        # Permission check
        if not self._permissions.has_permission(agent_perms, action):
            return GovernancePolicyResult(
                decision=GovernanceDecision.BLOCK,
                risk_level=RiskLevel.MEDIUM,
                policy_id="GOV-PERMISSION-DENIED",
                reasons=[f"Agent lacks permission: {action}"],
                blocked=True,
            )

        # Tool permission check
        for tool in request.tools_requested:
            if tool not in agent_perms and tool not in set(agent.tools_allowed):
                return GovernancePolicyResult(
                    decision=GovernanceDecision.BLOCK,
                    risk_level=RiskLevel.MEDIUM,
                    policy_id="GOV-TOOL-DENIED",
                    reasons=[f"Agent lacks tool permission: {tool}"],
                    blocked=True,
                )

        # Data access check
        allowed, reason = self._data_access.check(
            agent.data_classifications_allowed, request.data_classification
        )
        if not allowed:
            return GovernancePolicyResult(
                decision=GovernanceDecision.BLOCK,
                risk_level=RiskLevel.HIGH,
                policy_id="GOV-DATA-DENIED",
                reasons=[reason or "Data access denied"],
                blocked=True,
            )

        # Purpose check — must be non-empty for sensitive+ data
        if (
            request.data_classification.value in ("SENSITIVE", "RESTRICTED", "CRITICAL")
            and not request.purpose
        ):
            return GovernancePolicyResult(
                decision=GovernanceDecision.REVIEW_REQUIRED,
                risk_level=RiskLevel.HIGH,
                policy_id="GOV-PURPOSE-REQUIRED",
                reasons=["Purpose required for sensitive data access"],
                blocked=True,
            )

        # Risk classification
        risk = self._risk.classify(action, request.data_classification)

        # Exceeds agent max risk level
        if RISK_ORDER.index(risk) > RISK_ORDER.index(agent.max_risk_level):
            return GovernancePolicyResult(
                decision=GovernanceDecision.BLOCK,
                risk_level=risk,
                policy_id="GOV-RISK-EXCEEDED",
                reasons=[
                    f"Action risk {risk.value} exceeds agent max {agent.max_risk_level.value}"
                ],
                blocked=True,
            )

        # Human approval for high/critical or configured actions
        if self._permissions.requires_human_approval(
            action, set(agent.human_approval_required)
        ) or risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            if action in set(agent.human_approval_required) or risk == RiskLevel.CRITICAL:
                return GovernancePolicyResult(
                    decision=GovernanceDecision.HUMAN_APPROVAL_REQUIRED,
                    risk_level=risk,
                    policy_id="GOV-APPROVAL-REQUIRED",
                    reasons=[f"Human approval required for {action} (risk: {risk.value})"],
                    approval_required=True,
                )

        # Medium risk with restricted character → restrict
        if risk == RiskLevel.MEDIUM and action in set(agent.restricted_actions):
            return GovernancePolicyResult(
                decision=GovernanceDecision.RESTRICT,
                risk_level=risk,
                policy_id="GOV-RESTRICTED",
                reasons=[f"Action {action} is restricted — limited execution"],
                restricted=True,
            )

        return GovernancePolicyResult(
            decision=GovernanceDecision.ALLOW,
            risk_level=risk,
            policy_id="GOV-ALLOW",
            reasons=[f"Action {action} permitted"],
        )
