"""Base types for multi-agent routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from services.agent.models import AgentActivation


@dataclass(frozen=True)
class SpecialistDefinition:
    """A domain specialist activated by intent patterns."""

    id: str
    name: str
    description: str
    system_addendum: str
    patterns: tuple[str, ...] = ()
    input_types: tuple[str, ...] = ("text",)
    priority: int = 0
    is_enrichment: bool = False

    def score(self, prompt: str, *, input_type: str) -> int:
        if input_type not in self.input_types:
            return 0
        lower = prompt.lower()
        return sum(1 for pattern in self.patterns if re.search(pattern, lower))


@dataclass
class RoutingContext:
    """Inputs used to decide which agents should run."""

    prompt: str
    input_type: str = "text"
    use_web_search: bool = False


@dataclass
class RoutingPlan:
    """Agents to run and the composed LLM system prompt."""

    primary_id: str
    primary_name: str
    active_agents: list[AgentActivation] = field(default_factory=list)
    system_prompt: str = ""
    needs_web_search: bool = False
