"""Unit tests for services/auth: strict HS256 bearer-token role verification.

Every test exercises the trust boundary directly against verify_token /
mint_dev_token with locally crafted tokens. No network, no HTTP.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest

from services.auth import (
    AuthConfigError,
    AuthError,
    ensure_startup_requirements,
    is_dev_mode_enabled,
    mint_dev_token,
    verify_token,
)

SECRET = "unit-test-signing-secret"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)


def _encode(payload: dict, *, algorithm: str = "HS256", key: str = SECRET) -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


def _payload(**overrides):
    base = {
        "role": "researcher",
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
    }
    base.update(overrides)
    return base


def test_valid_token_round_trips_role():
    token = mint_dev_token("auditor")
    assert verify_token(token) == "auditor"


def test_minted_token_carries_exp_and_role():
    raw = mint_dev_token("clinician")
    claims = jwt.decode(raw, SECRET, algorithms=["HS256"])
    assert claims["role"] == "clinician"
    assert "exp" in claims


def test_expired_token_is_rejected():
    past = int((datetime.now(UTC) - timedelta(minutes=5)).timestamp())
    with pytest.raises(AuthError):
        verify_token(_encode(_payload(exp=past)))


def test_missing_exp_claim_is_rejected():
    payload = _payload()
    del payload["exp"]
    with pytest.raises(AuthError):
        verify_token(_encode(payload))


def test_tampered_signature_is_rejected():
    token = mint_dev_token("researcher")
    header, body, sig = token.split(".")
    tampered = f"{header}.{body}x{sig[:-1]}"  # flip payload + trim signature
    with pytest.raises(AuthError):
        verify_token(tampered)


def test_none_algorithm_is_rejected():
    # Explicit alg-confusion check: an unsigned token must never verify.
    token = _encode(_payload(), algorithm="none", key="")
    with pytest.raises(AuthError):
        verify_token(token)


def test_different_hs_algorithm_is_rejected():
    # Signed with HS384 using the correct secret; the HS256 pin must reject it.
    token = _encode(_payload(), algorithm="HS384")
    with pytest.raises(AuthError):
        verify_token(token)


def test_wrong_signing_secret_is_rejected():
    token = _encode(_payload(), key="some-other-secret")
    with pytest.raises(AuthError):
        verify_token(token)


def test_garbage_token_is_rejected():
    with pytest.raises(AuthError):
        verify_token("not-a-jwt")


@pytest.mark.parametrize("bad_role", [None, 123, ["admin"], "", "   "])
def test_invalid_role_claims_are_rejected(bad_role):
    with pytest.raises(AuthError):
        verify_token(_encode(_payload(role=bad_role)))


def test_role_is_stripped_of_surrounding_whitespace():
    token = mint_dev_token("  researcher  ")
    assert verify_token(token) == "researcher"


def test_dev_mode_default_is_off(monkeypatch):
    monkeypatch.delenv("AUTH_DEV_MODE", raising=False)
    assert is_dev_mode_enabled() is False


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes"])
def test_dev_mode_explicit_true_values(monkeypatch, value):
    monkeypatch.setenv("AUTH_DEV_MODE", value)
    assert is_dev_mode_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "", "on"])
def test_dev_mode_other_values_are_off(monkeypatch, value):
    monkeypatch.setenv("AUTH_DEV_MODE", value)
    assert is_dev_mode_enabled() is False


def test_startup_fails_when_dev_mode_off_and_no_secret(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        ensure_startup_requirements()
    assert "AUTH_JWT_SECRET" in str(excinfo.value)


def test_startup_succeeds_with_secret_when_dev_mode_off(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    ensure_startup_requirements()  # must not raise


def test_startup_succeeds_in_dev_mode_without_secret(monkeypatch):
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    ensure_startup_requirements()  # dev mode may start; minting will still fail


def test_minting_without_secret_raises_config_error(monkeypatch):
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    with pytest.raises(AuthConfigError):
        mint_dev_token("researcher")


def test_verify_without_secret_raises_config_error(monkeypatch):
    token = SimpleNamespace()  # placeholder to prove config error precedes decode
    del token
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    with pytest.raises(AuthConfigError):
        verify_token("whatever")
