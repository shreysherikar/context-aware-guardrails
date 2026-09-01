"""Tests for Safe Rewriting placeholder integration boundary."""

from domain.governance_models import AgentActionRequest, AgentIdentity
from services.governance.safe_rewrite import PassThroughSafeRewrite


def test_pass_through_preserves_request():
    pipeline = PassThroughSafeRewrite()
    req = AgentActionRequest(
        identity=AgentIdentity(
            agent_id="literature-research",
            agent_version="1.0.0",
            request_id="req-1",
            session_id="sess-1",
        ),
        requested_action="SEARCH_LITERATURE",
    )
    out = pipeline.process_request(req)
    assert out.requested_action == "SEARCH_LITERATURE"
    assert out.identity.agent_id == "literature-research"


def test_pass_through_preserves_output():
    pipeline = PassThroughSafeRewrite()
    data = {"answer": "test", "sources": []}
    assert pipeline.process_output(data) == data
