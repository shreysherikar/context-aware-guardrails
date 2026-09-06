"""Email/password authentication against AUTH_PASSWORD_USERS."""

import pytest

from services.auth import AuthError, authenticate_password
from services.auth.password import DEFAULT_DESKTOP_USERS


@pytest.fixture(autouse=True)
def _users(monkeypatch):
    monkeypatch.setenv(
        "AUTH_PASSWORD_USERS",
        "clinician@acme.com:secret:clinician,Admin@Acme.com:admin:admin",
    )


def test_matching_credentials_return_role_and_normalized_email():
    identity = authenticate_password("Clinician@Acme.com", "secret")
    assert identity.email == "clinician@acme.com"
    assert identity.role == "clinician"


def test_wrong_password_is_rejected():
    with pytest.raises(AuthError):
        authenticate_password("clinician@acme.com", "wrong")


def test_unknown_email_is_rejected():
    with pytest.raises(AuthError):
        authenticate_password("nobody@acme.com", "secret")


def test_empty_password_users_rejects_everyone(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD_USERS", "")
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.delenv("AUTH_DUMMY_LOGIN", raising=False)
    with pytest.raises(AuthError):
        authenticate_password("clinician@acme.com", "secret")


def test_dummy_account_works_in_dev_mode(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD_USERS", "")
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    identity = authenticate_password("demo@contextguard.local", "demo")
    assert identity.email == "demo@contextguard.local"
    assert identity.role == "clinician"


def test_dummy_account_works_when_flag_set(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD_USERS", "")
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.setenv("AUTH_DUMMY_LOGIN", "true")
    identity = authenticate_password("DEMO@contextguard.local", "demo")
    assert identity.role == "clinician"


def test_desktop_defaults_parse(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD_USERS", DEFAULT_DESKTOP_USERS)
    identity = authenticate_password("clinician@contextguard.local", "clinician")
    assert identity.email == "clinician@contextguard.local"
    assert identity.role == "clinician"
