"""Agent router unit tests."""

from services.agent.router import route_request
from services.agent.specialists.base import RoutingContext


def test_route_general_fallback():
    plan = route_request(RoutingContext(prompt="Hello there"))
    assert plan.primary_id == "general"
    assert any(a.id == "compliance_guard" for a in plan.active_agents)


def test_route_hcp_engagement():
    plan = route_request(
        RoutingContext(prompt="Draft a follow-up email template after an HCP call.")
    )
    assert plan.primary_id == "hcp_engagement"
    assert any(a.id == "hcp_engagement" for a in plan.active_agents)


def test_route_analytics():
    plan = route_request(
        RoutingContext(
            prompt="Using CRM in aggregate, summarize engagement performance by region and channel."
        )
    )
    assert plan.primary_id == "analytics"


def test_route_research_with_web_flag():
    plan = route_request(RoutingContext(prompt="What is our internal policy?", use_web_search=True))
    assert plan.needs_web_search is True
    assert any(a.id == "research" for a in plan.active_agents)


def test_route_optical_for_images():
    plan = route_request(RoutingContext(prompt="Patient Name: Jane Doe", input_type="image"))
    assert plan.primary_id == "optical"
    assert any(a.id == "optical" for a in plan.active_agents)


def test_route_compliance_coach_for_off_label():
    plan = route_request(
        RoutingContext(prompt="Create an HCP education summary for off-label use of Drug X.")
    )
    assert plan.primary_id == "compliance_coach"
