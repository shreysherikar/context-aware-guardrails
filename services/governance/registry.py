"""Central agent registry for pharmaceutical AI agents."""

from __future__ import annotations

from domain.governance_enums import AgentStatus
from domain.governance_models import AgentRegisterRequest, AgentRegistryEntry
from services.governance.registry_data import ALL_PHARMA_AGENTS


class AgentRegistry:
    """In-memory agent registry — pre-loaded with all pharma agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentRegistryEntry] = {}
        for agent in ALL_PHARMA_AGENTS:
            self._agents[agent.agent_id] = agent

    def register(self, entry: AgentRegisterRequest) -> AgentRegistryEntry:
        if entry.agent_id in self._agents:
            raise ValueError(f"Agent {entry.agent_id} already registered")
        agent = AgentRegistryEntry(
            agent_id=entry.agent_id,
            name=entry.name,
            agent_type=entry.agent_type,
            description=entry.description,
            owner=entry.owner,
            version=entry.version,
            capabilities=entry.capabilities,
            permissions=entry.permissions,
            restricted_actions=entry.restricted_actions,
            human_approval_required=entry.human_approval_required,
            data_classifications_allowed=entry.data_classifications_allowed,
            tools_allowed=entry.tools_allowed,
            computer_use_permissions=entry.computer_use_permissions,
            max_risk_level=entry.max_risk_level,
            audit_required=entry.audit_required,
            category=entry.category,
        )
        self._agents[agent.agent_id] = agent
        return agent

    def get(self, agent_id: str) -> AgentRegistryEntry | None:
        return self._agents.get(agent_id)

    def list_all(self) -> list[AgentRegistryEntry]:
        return list(self._agents.values())

    def list_active(self) -> list[AgentRegistryEntry]:
        return [a for a in self._agents.values() if a.status == AgentStatus.ACTIVE]

    def count(self) -> int:
        return len(self._agents)

    def update_status(self, agent_id: str, status: AgentStatus) -> None:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Agent {agent_id} not found")
        self._agents[agent_id] = agent.model_copy(update={"status": status})
