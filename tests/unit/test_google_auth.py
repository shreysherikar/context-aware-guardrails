"""Unit tests for services/auth/google_auth: Google ID-token verification and the
permanent email/domain allowlist.

No network, no live Google: the verifier's verify_fn is injected with fakes,
and the allowlist functions read environment variables (monkeypatched).
"""

import jwt
import pytest

from services.auth import (
    AuthConfigError,
    AuthError,
    GoogleAuthError,
    GoogleIdentity,
    default_role_for_email,
    get_google_verifier,
    is_email_allowed,
    mint_token,
    verify_token,
)

CLIENT_ID = "unit-test-google-client.apps.googleusercontent.com"
SECRET = "unit-test-signing-secret-0123456789abcdef"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("GOOGLE_ALLOWED_DOMAINS", raising=False)
    monkeypatch.delenv("GOOGLE_DEFAULT_ROLE", raising=False)


def _identity(email="alice@acme.com", *, subject="google-sub-123", email_verified=True):
    return GoogleIdentity(email=email, subject=subject, email_verified=email_verified)


# ---------------------------------------------------------------------------
# GoogleIdTokenVerifier (injected verify_fn — no network)
# ---------------------------------------------------------------------------


def test_valid_identity_passes_verification():
    verifier = get_google_verifier(client_id=CLIENT_ID, verify_fn=lambda cid, token: _identity())
    identity = verifier.verify_token("valid.id.token")
    assert identity.email == "alice@acme.com"
    assert identity.subject == "google-sub-123"
    assert identity.email_verified is True


def test_audience_mismatch_or_bad_signature_collapses_to_auth_error():
    def failing(cid, token):
        raise ValueError("Invalid token: audience mismatch")

    verifier = get_google_verifier(client_id=CLIENT_ID, verify_fn=failing)
    with pytest.raises(GoogleAuthError):
        verifier.verify_token("bad.token")


def test_provider_google_auth_error_passes_through():
    def failing(cid, token):
        raise GoogleAuthError("bad signature")

    verifier = get_google_verifier(client_id=CLIENT_ID, verify_fn=failing)
    with pytest.raises(AuthError):
        verifier.verify_token("bad.token")


def test_network_failure_collapses_to_auth_error():
    def failing(cid, token):
        raise ConnectionError("certificate fetch failed")

    verifier = get_google_verifier(client_id=CLIENT_ID, verify_fn=failing)
    with pytest.raises(AuthError):
        verifier.verify_token("bad.token")


def test_unconfigured_client_id_raises_config_error():
    verifier = get_google_verifier(client_id="")
    with pytest.raises(AuthConfigError):
        verifier.verify_token("any.token")


def test_unverified_email_is_rejected_even_when_signature_valid():
    verifier = get_google_verifier(
        client_id=CLIENT_ID,
        verify_fn=lambda cid, token: _identity(email_verified=False),
    )
    with pytest.raises(GoogleAuthError):
        verifier.verify_token("unverified.token")


def test_empty_or_missing_token_is_rejected():
    verifier = get_google_verifier(client_id=CLIENT_ID, verify_fn=lambda cid, token: _identity())
    with pytest.raises(AuthError):
        verifier.verify_token("")
    with pytest.raises(AuthError):
        verifier.verify_token(None)


# ---------------------------------------------------------------------------
# Permanent allowlist: is_email_allowed (fail closed)
# ---------------------------------------------------------------------------


def test_exact_email_match_is_allowed(monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "alice@acme.com")
    monkeypatch.delenv("GOOGLE_ALLOWED_DOMAINS", raising=False)
    assert is_email_allowed("alice@acme.com") is True


def test_domain_match_is_allowed(monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_DOMAINS", "acme.com")
    monkeypatch.delenv("GOOGLE_ALLOWED_EMAILS", raising=False)
    assert is_email_allowed("bob@acme.com") is True


def test_no_allowlist_configured_rejects_everyone(monkeypatch):
    monkeypatch.delenv("GOOGLE_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("GOOGLE_ALLOWED_DOMAINS", raising=False)
    assert is_email_allowed("employee@acme.com") is False


def test_empty_allowlist_variables_reject_everyone(monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "")
    monkeypatch.setenv("GOOGLE_ALLOWED_DOMAINS", "  ")
    assert is_email_allowed("employee@acme.com") is False


def test_non_matching_email_is_rejected(monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "alice@acme.com")
    monkeypatch.setenv("GOOGLE_ALLOWED_DOMAINS", "acme.com")
    assert is_email_allowed("mallory@other.com") is False


def test_allowlist_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "Alice@Acme.COM")
    monkeypatch.setenv("GOOGLE_ALLOWED_DOMAINS", "ACME.COM")
    assert is_email_allowed("alice@acme.com") is True  # exact email, case-insensitive
    assert is_email_allowed("ALICE@acme.com") is True
    assert is_email_allowed("BOB@acme.com") is True  # domain, case-insensitive


def test_email_subdomain_is_not_treated_as_domain_match(monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "")
    monkeypatch.setenv("GOOGLE_ALLOWED_DOMAINS", "acme.com")
    assert is_email_allowed("bob@sub.acme.com") is False


def test_degenerate_inputs_are_rejected(monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "alice@acme.com")
    monkeypatch.setenv("GOOGLE_ALLOWED_DOMAINS", "acme.com")
    assert is_email_allowed("") is False
    assert is_email_allowed("not-an-email") is False
    assert is_email_allowed(None) is False


def test_list_entries_are_stripped_of_whitespace(monkeypatch):
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", " alice@acme.com , bob@acme.com ")
    monkeypatch.setenv("GOOGLE_ALLOWED_DOMAINS", " acme.com ")
    assert is_email_allowed("alice@acme.com") is True
    assert is_email_allowed("bob@acme.com") is True


# ---------------------------------------------------------------------------
# Default role + minted-token subject
# ---------------------------------------------------------------------------


def test_default_role_for_email_is_employee(monkeypatch):
    monkeypatch.delenv("GOOGLE_DEFAULT_ROLE", raising=False)
    assert default_role_for_email("alice@acme.com") == "employee"


def test_default_role_reads_env_override(monkeypatch):
    monkeypatch.setenv("GOOGLE_DEFAULT_ROLE", "clinician")
    assert default_role_for_email("alice@acme.com") == "clinician"


def test_minted_google_token_carries_approved_role_and_subject():
    token = mint_token("employee", subject="alice@acme.com")
    claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert claims["role"] == "employee"
    assert claims["sub"] == "alice@acme.com"
    assert "exp" in claims
    assert verify_token(token) == "employee"


def test_mint_token_rejects_invalid_subject():
    with pytest.raises(AuthError):
        mint_token("employee", subject="  ")
