"""API-level auth tests: /guardrail/evaluate requires a valid bearer token.

Every test exercises the HTTP endpoint through TestClient to prove the
auth dependency (get_verified_role) is enforced end-to-end: downstream
components (classifier, policy engine) are never invoked on a 401, and
valid tokens propagate the correct role.  All tokens are minted in-process
via the auth module — no network calls, no /auth/dev-token HTTP dependency.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
from fastapi.testclient import TestClient

from apps.api import main as _main_module
from apps.api.main import app
from services.auth import mint_dev_token

client = TestClient(app)

ALLOW_PROMPT = "Summarize this internal document."
SECRET = "unit-test-signing-secret"  # matches tests/conftest.py


def _encode(payload: dict, algorithm: str = "HS256", key: str = SECRET) -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


def _payload(role: str = "researcher", **overrides):
    base = {
        "role": role,
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Missing / invalid token
# ---------------------------------------------------------------------------


def test_missing_token_returns_401(monkeypatch):
    """No Authorization header — 401 before anything else runs."""
    spy = SimpleNamespace(called=False)

    def fake_verify(header):
        spy.called = True
        return "researcher"

    app.dependency_overrides[None] = lambda: spy  # won't be reached
    try:
        result = client.post(
            "/guardrail/evaluate",
            json={"prompt": ALLOW_PROMPT, "conversation_id": "missing-token"},
            # no Authorization header
        )
    finally:
        app.dependency_overrides.clear()

    assert result.status_code == 401
    assert not spy.called


# ---------------------------------------------------------------------------
# Expired token
# ---------------------------------------------------------------------------


def test_expired_token_returns_401():
    past = int((datetime.now(UTC) - timedelta(minutes=5)).timestamp())
    token = _encode(_payload(exp=past))

    result = client.post(
        "/guardrail/evaluate",
        json={"prompt": ALLOW_PROMPT, "conversation_id": "expired"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert result.status_code == 401


# ---------------------------------------------------------------------------
# Tampered / bad signature
# ---------------------------------------------------------------------------


def test_tampered_signature_returns_401():
    token = _encode(_payload(), key="wrong-secret")
    result = client.post(
        "/guardrail/evaluate",
        json={"prompt": ALLOW_PROMPT, "conversation_id": "tampered"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert result.status_code == 401


# ---------------------------------------------------------------------------
# Valid JWT — role reaches PolicyEngine, client spoofing ignored
# ---------------------------------------------------------------------------


def test_valid_token_propagates_role_to_policy_engine(monkeypatch):
    """The verified token role, not any client-supplied value, is used."""
    received_role = None

    original_evaluate = _main_module.policy_engine.evaluate

    def spy_evaluate(*args, **kwargs):
        nonlocal received_role
        # PolicyEngine.evaluate signature: evaluate(risk_assessment, user_role, policy)
        received_role = kwargs.get("user_role") or (args[1] if len(args) > 1 else None)
        return original_evaluate(*args, **kwargs)

    monkeypatch.setattr(
        "apps.api.main.policy_engine.evaluate",
        spy_evaluate,
    )

    # mint a valid token for 'auditor'
    token = mint_dev_token("auditor")
    result = client.post(
        "/guardrail/evaluate",
        json={"prompt": ALLOW_PROMPT, "conversation_id": "role-check", "user_role": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert result.status_code == 200
    assert received_role == "auditor"


# ---------------------------------------------------------------------------
# Dev-token endpoint gated by AUTH_DEV_MODE
# ---------------------------------------------------------------------------


def test_dev_token_404_when_dev_mode_off():
    """With AUTH_DEV_MODE=false (the safe default), /auth/dev-token does not exist."""
    result = client.post("/auth/dev-token", json={"role": "researcher"})
    assert result.status_code == 404


def test_dev_token_works_and_produces_accepted_token(monkeypatch):
    """When AUTH_DEV_MODE=true, /auth/dev-token returns a usable token."""
    monkeypatch.setenv("AUTH_DEV_MODE", "true")

    from apps.api.main import app as reloaded_app

    reloaded = TestClient(reloaded_app)
    resp = reloaded.post("/auth/dev-token", json={"role": "clinician"})
    assert resp.status_code == 200
    token = resp.json()["token"]

    # the token must be accepted by verify_token
    from services.auth import verify_token

    assert verify_token(token) == "clinician"
