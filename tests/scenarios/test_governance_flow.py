"""Scenario tests for governance API endpoints."""

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_list_agents():
    resp = client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) >= 60
    ids = {a["agent_id"] for a in agents}
    assert "literature-research" in ids
    assert "pv-case-intake" in ids
    assert "mfg-batch-release" in ids


def test_get_agent():
    resp = client.get("/agents/literature-research")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Literature Research Agent"


def test_system_status():
    resp = client.get("/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is True
    assert data["agents_registered"] >= 60


def test_policy_evaluate_allow():
    resp = client.post("/policy/evaluate", json={
        "agent_id": "literature-research",
        "requested_action": "SEARCH_LITERATURE",
        "data_classification": "PUBLIC",
        "purpose": "Literature review",
    })
    assert resp.status_code == 200
    assert resp.json()["decision"] == "ALLOW"


def test_policy_evaluate_block_escalation():
    resp = client.post("/policy/evaluate", json={
        "agent_id": "literature-research",
        "requested_action": "CHANGE_AGENT_PERMISSIONS",
        "data_classification": "INTERNAL",
    })
    assert resp.status_code == 200
    assert resp.json()["decision"] == "BLOCK"


def test_agent_request_high_risk_approval():
    resp = client.post("/agents/mfg-batch-release/request", json={
        "agent_id": "mfg-batch-release",
        "agent_version": "1.0.0",
        "request_id": "req-batch-1",
        "session_id": "sess-1",
        "requested_action": "RELEASE_BATCH",
        "data_classification": "CRITICAL",
        "purpose": "Batch release review",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "HUMAN_APPROVAL_REQUIRED"
    assert data["approval_id"] is not None


def test_approval_workflow():
    req = client.post("/agents/pv-case-intake/request", json={
        "agent_id": "pv-case-intake",
        "agent_version": "1.0.0",
        "request_id": "req-pv-1",
        "session_id": "sess-1",
        "requested_action": "FINALIZE_CASE",
        "data_classification": "SENSITIVE",
        "purpose": "Case finalization",
    })
    approval_id = req.json()["approval_id"]
    assert approval_id

    approve = client.post(f"/approval/{approval_id}/approve", json={"approver": "qa-lead"})
    assert approve.status_code == 200
    assert approve.json()["approval_status"] == "APPROVED"


def test_security_events_generated():
    client.post("/policy/evaluate", json={
        "agent_id": "literature-research",
        "requested_action": "DISABLE_GOVERNANCE",
        "data_classification": "INTERNAL",
    })
    resp = client.get("/security/events")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_governance_audit_logged():
    client.post("/policy/evaluate", json={
        "agent_id": "literature-research",
        "requested_action": "SEARCH_LITERATURE",
        "data_classification": "PUBLIC",
        "purpose": "Audit test",
    })
    resp = client.get("/audit")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_safe_rewrite_placeholder_allows_flow():
    """Future Safe Rewriting module integration point must not break governance."""
    resp = client.post("/policy/evaluate", json={
        "agent_id": "literature-research",
        "requested_action": "CREATE_DRAFT",
        "data_classification": "INTERNAL",
        "purpose": "Draft report",
    })
    assert resp.status_code == 200
    assert resp.json()["decision"] in ("ALLOW", "RESTRICT")
