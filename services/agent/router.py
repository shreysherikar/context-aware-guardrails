"""Route requests to the specialist agents that should handle them."""

from __future__ import annotations

from services.agent.models import AgentActivation
from services.agent.specialists.base import RoutingContext, RoutingPlan, SpecialistDefinition
from services.agent.specialists.registry import (
    ALL_SPECIALISTS,
    COMPLIANCE_GUARD,
    GENERAL_AGENT,
    OPTICAL_AGENT,
    RESEARCH_AGENT,
    SHARED_BASE_PROMPT,
    SPECIALIST_BY_ID,
)
from services.web_bridge.search import should_search_web


def route_request(ctx: RoutingContext) -> RoutingPlan:
    """Pick active agents and compose the system prompt for generation."""
    active: list[AgentActivation] = [
        AgentActivation(
            id=COMPLIANCE_GUARD.id,
            name=COMPLIANCE_GUARD.name,
            role="guard",
        )
    ]

    scored: list[tuple[int, int, SpecialistDefinition]] = []
    for spec in ALL_SPECIALISTS:
        if spec.id == COMPLIANCE_GUARD.id:
            continue
        score = spec.score(ctx.prompt, input_type=ctx.input_type)
        if score > 0:
            scored.append((score, spec.priority, spec))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

    matched = [spec for _, _, spec in scored]
    if ctx.input_type == "image" and OPTICAL_AGENT not in matched:
        matched.insert(0, OPTICAL_AGENT)

    if not matched:
        matched = [GENERAL_AGENT]

    primary = matched[0]
    for spec in matched:
        role = "enrichment" if spec.is_enrichment else "specialist"
        active.append(AgentActivation(id=spec.id, name=spec.name, role=role))

    # Research enrichment also runs when the UI flag or auto-triggers fire.
    needs_web_search = ctx.use_web_search or should_search_web(
        ctx.prompt, explicit=ctx.use_web_search
    )
    if needs_web_search and RESEARCH_AGENT.id not in {a.id for a in active}:
        active.append(
            AgentActivation(id=RESEARCH_AGENT.id, name=RESEARCH_AGENT.name, role="enrichment")
        )

    system_prompt = _compose_system_prompt(primary=primary, supporters=matched[1:])
    return RoutingPlan(
        primary_id=primary.id,
        primary_name=primary.name,
        active_agents=active,
        system_prompt=system_prompt,
        needs_web_search=needs_web_search,
    )


def _compose_system_prompt(
    *,
    primary: SpecialistDefinition,
    supporters: list[SpecialistDefinition],
) -> str:
    parts = [SHARED_BASE_PROMPT.strip(), "", f"Primary specialist: {primary.name}"]
    if primary.system_addendum:
        parts.append(primary.system_addendum)

    if supporters:
        parts.append("")
        parts.append("Supporting specialists consulted for this request:")
        for spec in supporters:
            parts.append(f"- {spec.name}: {spec.description}")

    return "\n".join(parts)


def specialist_label(agent_id: str) -> str:
    spec = SPECIALIST_BY_ID.get(agent_id)
    return spec.name if spec else agent_id
