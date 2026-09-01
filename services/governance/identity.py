"""Agent identity verification layer."""

from __future__ import annotations

from domain.governance_enums import AgentStatus, GovernanceDecision, SecurityEventCategory
from domain.governance_models import AgentActionRequest, AgentIdentity, SecurityEvent
from services.governance.registry import AgentRegistry
from services.governance.security_events import SecurityEventStore


class IdentityLayer:
    """Verify agent identity on every request — no shared unrestricted credentials."""

    def __init__(self, registry: AgentRegistry, events: SecurityEventStore) -> None:
        self._registry = registry
        self._events = events

    def verify(self, identity: AgentIdentity) -> tuple[bool, str | None, SecurityEvent | None]:
        if not identity.agent_id or not identity.request_id or not identity.session_id:
            event = self._events.record(
                agent_id=identity.agent_id or "unknown",
                category=SecurityEventCategory.AUTH_FAILURE,
                description="Missing required identity fields",
                request_id=identity.request_id,
                policy_decision=GovernanceDecision.REVIEW_REQUIRED,
            )
            return False, "Agent identity cannot be verified — missing required fields", event

        agent = self._registry.get(identity.agent_id)
        if agent is None:
            event = self._events.record(
                agent_id=identity.agent_id,
                category=SecurityEventCategory.AUTH_FAILURE,
                description=f"Unknown agent: {identity.agent_id}",
                request_id=identity.request_id,
                policy_decision=GovernanceDecision.BLOCK,
            )
            return False, f"Unknown agent: {identity.agent_id}", event

        if agent.status != AgentStatus.ACTIVE:
            event = self._events.record(
                agent_id=identity.agent_id,
                category=SecurityEventCategory.AUTH_FAILURE,
                description=f"Agent {identity.agent_id} is {agent.status.value}",
                request_id=identity.request_id,
                policy_decision=GovernanceDecision.BLOCK,
            )
            return False, f"Agent {identity.agent_id} is not active", event

        if identity.agent_version != agent.version:
            return False, f"Agent version mismatch: expected {agent.version}", None

        return True, None, None
