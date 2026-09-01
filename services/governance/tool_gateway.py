"""Extensible tool gateway — unified authorization for all tool adapters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from domain.governance_enums import GovernanceDecision
from domain.governance_models import AgentRegistryEntry, GovernedRequest, GovernanceResponse
from services.cyber_safety.darkweb import assess_darkweb_content, extract_text_for_assessment

logger = logging.getLogger(__name__)


class ToolAdapter(ABC):
    """Base adapter — every tool enforces the same governance mechanism."""

    name: str

    @abstractmethod
    def can_handle(self, action: str) -> bool:
        ...

    @abstractmethod
    def execute(
        self,
        governed: GovernedRequest,
        agent: AgentRegistryEntry,
        *,
        approved: bool = False,
    ) -> dict[str, Any]:
        ...


class APIToolAdapter(ToolAdapter):
    name = "api"

    def can_handle(self, action: str) -> bool:
        return action in ("EXTERNAL_API_CALL", "SEARCH_LITERATURE", "SEARCH_PATENTS")

    def execute(
        self,
        governed: GovernedRequest,
        agent: AgentRegistryEntry,
        *,
        approved: bool = False,
    ) -> dict[str, Any]:
        return {
            "tool": self.name,
            "action": governed.action,
            "status": "simulated",
            "request_id": governed.request_id,
        }


class FileToolAdapter(ToolAdapter):
    name = "file"

    def can_handle(self, action: str) -> bool:
        return action.startswith("READ_") or action in ("EDIT_DOCUMENT", "CREATE_DRAFT")

    def execute(
        self,
        governed: GovernedRequest,
        agent: AgentRegistryEntry,
        *,
        approved: bool = False,
    ) -> dict[str, Any]:
        return {
            "tool": self.name,
            "action": governed.action,
            "resource": governed.resource,
            "status": "simulated",
            "request_id": governed.request_id,
        }


class DatabaseToolAdapter(ToolAdapter):
    name = "database"

    def can_handle(self, action: str) -> bool:
        return action.startswith("ACCESS_") or action.startswith("READ_")

    def execute(
        self,
        governed: GovernedRequest,
        agent: AgentRegistryEntry,
        *,
        approved: bool = False,
    ) -> dict[str, Any]:
        return {
            "tool": self.name,
            "action": governed.action,
            "status": "simulated",
            "request_id": governed.request_id,
        }


class ComputerUseToolAdapter(ToolAdapter):
    name = "computer_use"

    def __init__(self, computer_engine: Any) -> None:
        self._computer = computer_engine

    def can_handle(self, action: str) -> bool:
        return action.startswith("COMPUTER_")

    def execute(
        self,
        governed: GovernedRequest,
        agent: AgentRegistryEntry,
        *,
        approved: bool = False,
    ) -> dict[str, Any]:
        session_id = governed.arguments.get("session_id", governed.session_id)
        result = self._computer.execute_action(session_id, governed, agent)
        return {
            "tool": self.name,
            "action": governed.action,
            "decision": result.decision.value,
            "executed": result.executed,
            "reason": result.reason,
            "request_id": governed.request_id,
        }


class PharmaSystemAdapter(ToolAdapter):
    """Adapter for LIMS, EDC, CTMS, QMS, MES, ERP."""

    def __init__(self, system_name: str) -> None:
        self.name = system_name
        self._prefix = f"ACCESS_{system_name.upper()}"

    def can_handle(self, action: str) -> bool:
        return action == self._prefix or action.startswith(f"READ_{self.name.upper()}")

    def execute(
        self,
        governed: GovernedRequest,
        agent: AgentRegistryEntry,
        *,
        approved: bool = False,
    ) -> dict[str, Any]:
        return {
            "tool": self.name,
            "action": governed.action,
            "status": "simulated",
            "request_id": governed.request_id,
        }


class ToolGateway:
    """
    Common gateway for all tool types.
    Every adapter enforces the same authorization and policy mechanism.
    """

    def __init__(self, adapters: list[ToolAdapter] | None = None) -> None:
        self._adapters: list[ToolAdapter] = adapters or []

    def register(self, adapter: ToolAdapter) -> None:
        self._adapters.append(adapter)

    def find_adapter(self, action: str) -> ToolAdapter | None:
        for adapter in self._adapters:
            if adapter.can_handle(action):
                return adapter
        return None

    def invoke(
        self,
        governed: GovernedRequest,
        agent: AgentRegistryEntry,
        governance_response: GovernanceResponse,
    ) -> dict[str, Any]:
        if governance_response.blocked:
            return {
                "error": "blocked",
                "reason": "; ".join(governance_response.reasons),
                "request_id": governed.request_id,
            }
        if governance_response.approval_required and not governance_response.approval_id:
            return {
                "error": "approval_required",
                "approval_id": governance_response.approval_id,
                "request_id": governed.request_id,
            }
        assessable = extract_text_for_assessment(
            governed.arguments,
            action=governed.action,
            purpose=governed.purpose or "",
            resource=governed.resource or "",
        )
        darkweb = assess_darkweb_content(
            assessable or governed.action,
            is_tool_request=True,
            is_computer_action=governed.action.startswith("COMPUTER_"),
        )
        if darkweb.decision == "BLOCK":
            return {
                "error": "blocked",
                "policy_id": "DARKWEB_ACCESS_PREVENTION",
                "reason": "; ".join(darkweb.reasons) or "Dark-web access prevention",
                "request_id": governed.request_id,
            }
        adapter = self.find_adapter(governed.action)
        if adapter is None:
            return {
                "error": "no_adapter",
                "action": governed.action,
                "request_id": governed.request_id,
            }
        approved = governance_response.decision in (
            GovernanceDecision.ALLOW,
            GovernanceDecision.ALLOW_WITH_RESTRICTIONS,
            GovernanceDecision.RESTRICT,
        )
        return adapter.execute(governed, agent, approved=approved)


def build_default_tool_gateway(computer_engine: Any) -> ToolGateway:
    gateway = ToolGateway()
    gateway.register(APIToolAdapter())
    gateway.register(FileToolAdapter())
    gateway.register(DatabaseToolAdapter())
    gateway.register(ComputerUseToolAdapter(computer_engine))
    for system in ("LIMS", "EDC", "CTMS", "QMS", "MES", "ERP"):
        gateway.register(PharmaSystemAdapter(system))
    return gateway
