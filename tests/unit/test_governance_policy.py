"""Unit tests for governance policy engine."""

import pytest

from domain.enums import RiskLevel
from domain.governance_enums import DataClassification, GovernanceDecision
from domain.governance_models import AgentActionRequest, AgentIdentity, AgentRegistryEntry
from services.governance.policy import GovernancePolicyEngine


@pytest.fixture
def policy():
    return GovernancePolicyEngine()


@pytest.fixture
def literature_agent():
    return AgentRegistryEntry(
        agent_id="literature-research",
        name="Literature Research Agent",
        agent_type="research",
        description="Read-only literature search",
        permissions=["READ_LITERATURE", "SEARCH_LITERATURE", "CREATE_DRAFT"],
        data_classifications_allowed=[DataClassification.PUBLIC, DataClassification.INTERNAL],
        max_risk_level=RiskLevel.LOW,
    )


@pytest.fixture
def pv_agent():
    return AgentRegistryEntry(
        agent_id="pv-case-intake",
        name="Case Intake Agent",
        agent_type="pv",
        description="PV case intake",
        permissions=["READ_SAFETY_REPORTS", "CREATE_SAFETY_CASE"],
        human_approval_required=["FINALIZE_CASE"],
        restricted_actions=["FINALIZE_CASE"],
        data_classifications_allowed=[DataClassification.SENSITIVE],
        max_risk_level=RiskLevel.HIGH,
    )


def _req(action, agent_id="literature-research", data_class=DataClassification.INTERNAL):
    return AgentActionRequest(
        identity=AgentIdentity(
            agent_id=agent_id,
            agent_version="1.0.0",
            request_id="req-1",
            session_id="sess-1",
        ),
        requested_action=action,
        data_classification=data_class,
        purpose="Research summary",
    )


def test_low_risk_allowed(policy, literature_agent):
    result = policy.evaluate(literature_agent, _req("SEARCH_LITERATURE"))
    assert result.decision == GovernanceDecision.ALLOW


def test_unauthorized_action_blocked(policy, literature_agent):
    result = policy.evaluate(literature_agent, _req("CREATE_SAFETY_CASE"))
    assert result.decision == GovernanceDecision.BLOCK
    assert result.blocked


def test_restricted_data_without_purpose_review_required(policy, literature_agent):
    result = policy.evaluate(
        literature_agent,
        AgentActionRequest(
            identity=_req("READ_LITERATURE").identity,
            requested_action="READ_LITERATURE",
            data_classification=DataClassification.RESTRICTED,
        ),
    )
    assert result.decision in (GovernanceDecision.BLOCK, GovernanceDecision.REVIEW_REQUIRED)


def test_finalize_case_requires_approval(policy, pv_agent):
    result = policy.evaluate(
        pv_agent,
        _req("FINALIZE_CASE", agent_id="pv-case-intake", data_class=DataClassification.SENSITIVE),
    )
    assert result.decision == GovernanceDecision.HUMAN_APPROVAL_REQUIRED
    assert result.approval_required
