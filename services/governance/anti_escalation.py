"""Anti-privilege-escalation checks — agents must never self-elevate."""

from __future__ import annotations

from domain.governance_enums import GovernanceDecision, RestrictedAction, SecurityEventCategory
from domain.governance_models import AgentActionRequest, SecurityEvent
from services.governance.security_events import SecurityEventStore

ESCALATION_ACTIONS: frozenset[str] = frozenset(
    {
        RestrictedAction.CHANGE_AGENT_PERMISSIONS.value,
        RestrictedAction.MODIFY_AGENT_REGISTRY.value,
        RestrictedAction.MODIFY_ANOTHER_AGENT_PERMISSIONS.value,
        RestrictedAction.CHANGE_SECURITY_POLICY.value,
        RestrictedAction.DISABLE_GOVERNANCE.value,
        RestrictedAction.DISABLE_LOGGING.value,
        RestrictedAction.DELETE_AUDIT_RECORD.value,
        RestrictedAction.CREATE_UNRESTRICTED_CREDENTIALS.value,
        RestrictedAction.DISABLE_HUMAN_APPROVAL.value,
        RestrictedAction.EMERGENCY_STOP.value,
    }
)


class AntiEscalationGuard:
    def __init__(self, events: SecurityEventStore) -> None:
        self._events = events

    def check(self, request: AgentActionRequest) -> tuple[bool, SecurityEvent | None]:
        action = request.requested_action
        if action not in ESCALATION_ACTIONS:
            return True, None

        event = self._events.record(
            agent_id=request.identity.agent_id,
            category=SecurityEventCategory.PRIVILEGE_ESCALATION,
            description=f"Privilege escalation attempt: {action}",
            request_id=request.identity.request_id,
            policy_decision=GovernanceDecision.BLOCK,
            evidence={"requested_action": action, "resource": request.requested_resource},
        )
        return False, event
