"""Unit tests for governed computer-use capability."""

from datetime import UTC

import pytest

from domain.enums import RiskLevel
from domain.governance_enums import ComputerPermission, GovernanceDecision
from domain.governance_models import AgentRegistryEntry, GovernedRequest
from services.governance.approval import ApprovalStore
from services.governance.computer_use.engine import ComputerUseEngine
from services.governance.computer_use.sandbox import ComputerSandbox
from services.governance.computer_use.sessions import ComputerSessionStore
from services.governance.kill_switch import KillSwitch


@pytest.fixture
def agent():
    return AgentRegistryEntry(
        agent_id="clinical-data-agent",
        name="Clinical Data Agent",
        agent_type="clinical",
        description="Clinical data review",
        category="clinical",
        permissions=[
            ComputerPermission.COMPUTER_VIEW_SCREEN.value,
            ComputerPermission.COMPUTER_CLICK.value,
            ComputerPermission.COMPUTER_TYPE.value,
            ComputerPermission.COMPUTER_BROWSER_NAVIGATION.value,
            ComputerPermission.COMPUTER_READ_FILE.value,
        ],
        computer_use_permissions=[
            ComputerPermission.COMPUTER_VIEW_SCREEN.value,
            ComputerPermission.COMPUTER_CLICK.value,
            ComputerPermission.COMPUTER_TYPE.value,
            ComputerPermission.COMPUTER_BROWSER_NAVIGATION.value,
            ComputerPermission.COMPUTER_READ_FILE.value,
        ],
        max_risk_level=RiskLevel.HIGH,
    )


@pytest.fixture
def engine():
    return ComputerUseEngine(sessions=ComputerSessionStore(), kill_switch=KillSwitch())


@pytest.fixture
def engine_with_approvals():
    return ComputerUseEngine(
        sessions=ComputerSessionStore(),
        kill_switch=KillSwitch(),
        approvals=ApprovalStore(),
    )


def _governed(action, session_id, **kwargs):
    return GovernedRequest(
        request_id=kwargs.get("request_id", "req-cu-1"),
        session_id=session_id,
        agent_id="clinical-data-agent",
        agent_version="1.0.0",
        action=action,
        resource=kwargs.get("target"),
        arguments=kwargs.get("arguments", {}),
    )


def test_low_risk_action_allowed(engine, agent):
    session = engine.create_session(agent, allowed_domains=["intranet.pharma.local"])
    result = engine.execute_action(
        session.session_id,
        _governed(
            ComputerPermission.COMPUTER_VIEW_SCREEN.value,
            session.session_id,
        ),
        agent,
    )
    assert result.decision == GovernanceDecision.ALLOW
    assert result.executed


def test_unauthorized_click_blocked(engine, agent):
    limited = agent.model_copy(
        update={
            "computer_use_permissions": [ComputerPermission.COMPUTER_VIEW_SCREEN.value],
            "permissions": [ComputerPermission.COMPUTER_VIEW_SCREEN.value],
        }
    )
    session = engine.create_session(limited)
    result = engine.execute_action(
        session.session_id,
        _governed(ComputerPermission.COMPUTER_CLICK.value, session.session_id),
        limited,
    )
    assert result.decision == GovernanceDecision.BLOCK


def test_restricted_domain_blocked(engine, agent):
    session = engine.create_session(agent, allowed_domains=["intranet.pharma.local"])
    result = engine.execute_action(
        session.session_id,
        _governed(
            ComputerPermission.COMPUTER_BROWSER_NAVIGATION.value,
            session.session_id,
            target="evil-exfil.com",
            arguments={"domain": "evil-exfil.com"},
        ),
        agent,
    )
    assert result.decision == GovernanceDecision.BLOCK


def test_approved_domain_allowed(engine, agent):
    session = engine.create_session(agent, allowed_domains=["intranet.pharma.local"])
    result = engine.execute_action(
        session.session_id,
        _governed(
            ComputerPermission.COMPUTER_BROWSER_NAVIGATION.value,
            session.session_id,
            arguments={"domain": "intranet.pharma.local"},
        ),
        agent,
    )
    assert result.decision == GovernanceDecision.ALLOW


def test_critical_action_requires_approval(engine, agent):
    agent_full = agent.model_copy(
        update={
            "computer_use_permissions": list(agent.computer_use_permissions)
            + [ComputerPermission.COMPUTER_EXECUTE_COMMAND.value],
            "permissions": list(agent.permissions)
            + [ComputerPermission.COMPUTER_EXECUTE_COMMAND.value],
        }
    )
    session = engine.create_session(agent_full, risk_limit=RiskLevel.CRITICAL)
    result = engine.execute_action(
        session.session_id,
        _governed(
            ComputerPermission.COMPUTER_EXECUTE_COMMAND.value,
            session.session_id,
            arguments={"command": "rm -rf /"},
        ),
        agent_full,
    )
    assert result.decision == GovernanceDecision.HUMAN_APPROVAL_REQUIRED


def test_session_expiration(engine, agent):
    session = engine.create_session(agent, ttl_minutes=1)
    from datetime import datetime, timedelta

    expired = session.model_copy(update={"expiry_time": datetime.now(UTC) - timedelta(seconds=1)})
    engine._sessions._sessions[session.session_id] = expired
    result = engine.execute_action(
        session.session_id,
        _governed(ComputerPermission.COMPUTER_VIEW_SCREEN.value, session.session_id),
        agent,
    )
    assert result.decision == GovernanceDecision.BLOCK
    assert "expired" in result.reason.lower()


def test_kill_switch_blocks_all(engine, agent):
    session = engine.create_session(agent)
    engine._kill_switch.activate(reason="test")
    result = engine.execute_action(
        session.session_id,
        _governed(ComputerPermission.COMPUTER_VIEW_SCREEN.value, session.session_id),
        agent,
    )
    assert result.decision == GovernanceDecision.BLOCK
    engine._kill_switch.deactivate()


def test_blocked_directory(engine, agent):
    sandbox = ComputerSandbox()
    ok, reason = sandbox.validate_path("/etc/passwd", write=False)
    assert not ok


def test_sandbox_approval_required():
    sandbox = ComputerSandbox()
    assert sandbox.action_requires_approval(ComputerPermission.COMPUTER_EXECUTE_COMMAND.value)


def test_high_risk_upload_requires_approval(engine_with_approvals, agent):
    agent_full = agent.model_copy(
        update={
            "computer_use_permissions": list(agent.computer_use_permissions)
            + [ComputerPermission.COMPUTER_UPLOAD_FILE.value],
            "permissions": list(agent.permissions)
            + [ComputerPermission.COMPUTER_UPLOAD_FILE.value],
        }
    )
    session = engine_with_approvals.create_session(
        agent_full,
        allowed_directories=["/sandbox"],
        risk_limit=RiskLevel.HIGH,
    )
    result = engine_with_approvals.execute_action(
        session.session_id,
        _governed(
            ComputerPermission.COMPUTER_UPLOAD_FILE.value,
            session.session_id,
            target="/sandbox/upload.csv",
            arguments={"path": "/sandbox/upload.csv"},
        ),
        agent_full,
    )
    assert result.decision == GovernanceDecision.HUMAN_APPROVAL_REQUIRED
    assert result.approval_id is not None
    assert result.log_id is not None


def test_approved_high_risk_action_executes(engine_with_approvals, agent):
    agent_full = agent.model_copy(
        update={
            "computer_use_permissions": list(agent.computer_use_permissions)
            + [ComputerPermission.COMPUTER_UPLOAD_FILE.value],
            "permissions": list(agent.permissions)
            + [ComputerPermission.COMPUTER_UPLOAD_FILE.value],
        }
    )
    session = engine_with_approvals.create_session(
        agent_full,
        allowed_directories=["/sandbox"],
        risk_limit=RiskLevel.HIGH,
    )
    request_id = "req-upload-approved"
    pending = engine_with_approvals.execute_action(
        session.session_id,
        _governed(
            ComputerPermission.COMPUTER_UPLOAD_FILE.value,
            session.session_id,
            request_id=request_id,
            target="/sandbox/upload.csv",
            arguments={"path": "/sandbox/upload.csv"},
        ),
        agent_full,
    )
    approval_id = pending.approval_id
    assert approval_id
    engine_with_approvals._approvals.approve(approval_id, "reviewer")
    result = engine_with_approvals.execute_action(
        session.session_id,
        _governed(
            ComputerPermission.COMPUTER_UPLOAD_FILE.value,
            session.session_id,
            request_id=request_id,
            target="/sandbox/upload.csv",
            arguments={"path": "/sandbox/upload.csv"},
        ),
        agent_full,
        approval_id=approval_id,
    )
    assert result.decision == GovernanceDecision.ALLOW
    assert result.executed


def test_action_log_records_attempts(engine, agent):
    session = engine.create_session(agent)
    engine.execute_action(
        session.session_id,
        _governed(ComputerPermission.COMPUTER_VIEW_SCREEN.value, session.session_id),
        agent,
    )
    logs = engine.list_action_log(session_id=session.session_id)
    assert len(logs) == 1
    assert logs[0].action == ComputerPermission.COMPUTER_VIEW_SCREEN.value
    assert logs[0].decision == GovernanceDecision.ALLOW


def test_environment_session_defaults(engine, agent):
    session = engine.create_session(agent, environment_id="clinical-readonly")
    assert session.environment_id == "clinical-readonly"
    assert "edc.pharma.local" in session.allowed_domains
    assert session.risk_limit == RiskLevel.LOW
