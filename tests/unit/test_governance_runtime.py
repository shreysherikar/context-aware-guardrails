"""Unit tests for governance runtime — security-critical paths."""

import pytest

from domain.enums import RiskLevel
from domain.governance_enums import DataClassification, GovernanceDecision
from domain.governance_models import AgentActionRequest, AgentIdentity
from services.governance.approval import ApprovalStore
from services.governance.audit import GovernanceAuditStore
from services.governance.registry import AgentRegistry
from services.governance.runtime import GovernanceRuntime
from services.governance.security_events import SecurityEventStore


@pytest.fixture
def runtime(tmp_path):
    return GovernanceRuntime(
        registry=AgentRegistry(),
        audit=GovernanceAuditStore(db_path=tmp_path / "gov_audit.db"),
        approvals=ApprovalStore(),
        events=SecurityEventStore(),
    )


def _req(action, agent_id="literature-research", purpose="Research"):
    return AgentActionRequest(
        identity=AgentIdentity(
            agent_id=agent_id,
            agent_version="1.0.0",
            request_id=f"req-{action}",
            session_id="sess-1",
            user_id="user-1",
        ),
        requested_action=action,
        data_classification=DataClassification.INTERNAL,
        purpose=purpose,
    )


def test_all_pharma_agents_registered(runtime):
    assert runtime._registry.count() >= 60


def test_safe_low_risk_allowed(runtime):
    resp = runtime.process_request(_req("SEARCH_LITERATURE"))
    assert resp.decision == GovernanceDecision.ALLOW
    assert not resp.blocked
    assert resp.audit_id is not None


def test_unauthorized_action_blocked(runtime):
    resp = runtime.process_request(_req("RELEASE_BATCH", agent_id="literature-research"))
    assert resp.decision in (GovernanceDecision.BLOCK, GovernanceDecision.HUMAN_APPROVAL_REQUIRED)
    assert resp.decision != GovernanceDecision.ALLOW


def test_privilege_escalation_blocked(runtime):
    resp = runtime.process_request(_req("CHANGE_AGENT_PERMISSIONS"))
    assert resp.decision == GovernanceDecision.BLOCK
    assert resp.security_event_id is not None


def test_disable_governance_blocked(runtime):
    resp = runtime.process_request(_req("DISABLE_GOVERNANCE"))
    assert resp.decision == GovernanceDecision.BLOCK


def test_unknown_agent_blocked(runtime):
    resp = runtime.process_request(_req("READ_LITERATURE", agent_id="nonexistent-agent"))
    assert resp.blocked


def test_high_risk_requires_approval(runtime):
    resp = runtime.process_request(
        _req("RELEASE_BATCH", agent_id="mfg-batch-release", purpose="Batch QA review")
    )
    assert resp.decision == GovernanceDecision.HUMAN_APPROVAL_REQUIRED
    assert resp.approval_id is not None


def test_approval_missing_blocks_execution(runtime):
    resp = runtime.process_request(
        _req("RELEASE_BATCH", agent_id="mfg-batch-release", purpose="Batch release")
    )
    assert resp.approval_required
    assert not runtime._approvals.is_valid(resp.approval_id)


def test_policy_engine_unavailable_fail_closed(runtime):
    runtime._policy_enabled = False
    resp = runtime.process_request(_req("SEARCH_LITERATURE"))
    assert resp.decision == GovernanceDecision.REVIEW_REQUIRED
    assert resp.blocked


def test_audit_unavailable_fail_closed(runtime):
    class BrokenAudit:
        available = False

        def append(self, record):
            raise RuntimeError("audit down")

    runtime._audit = BrokenAudit()  # type: ignore[assignment]
    resp = runtime.process_request(_req("SEARCH_LITERATURE"))
    assert resp.decision == GovernanceDecision.REVIEW_REQUIRED
    assert resp.blocked


def test_runtime_stays_active(runtime):
    assert runtime.active
    status = runtime.get_status()
    assert status.active
    assert status.agents_registered >= 60


def test_concurrent_requests(runtime):
    for i in range(5):
        req = AgentActionRequest(
            identity=AgentIdentity(
                agent_id="literature-research",
                agent_version="1.0.0",
                request_id=f"concurrent-{i}",
                session_id="sess-1",
            ),
            requested_action="SEARCH_LITERATURE",
            data_classification=DataClassification.PUBLIC,
            purpose="Concurrent test",
        )
        resp = runtime.process_request(req)
        assert resp.decision == GovernanceDecision.ALLOW
