"""Google ID-token verification and the permanent sign-in allowlist (services/auth).

This module verifies Google OAuth2 ID tokens server-side (signature + audience)
against OUR GOOGLE_CLIENT_ID, then applies an operator-managed authorization
allowlist (GOOGLE_ALLOWED_EMAILS / GOOGLE_ALLOWED_DOMAINS) BEFORE any
context-aware-guardrail token is minted.

The allowlist is a real, permanent authorization decision — it does not depend
on the Google Cloud Console app's "Testing" status. FAIL CLOSED: when BOTH
allowlist variables are unset/empty, ``is_email_allowed()`` returns False for
everyone, so an unconfigured deployment rejects all Google sign-ins with 403
instead of accidentally opening the door.

The default verification function (``_verify_google_id_token``) imports
google-auth lazily so the app — and the test suite — remain importable without
the provider package installed. Provider SDK calls stay behind this function,
never in apps/api (matching the classifier-behind-an-interface pattern).
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.auth.core import AuthConfigError, AuthError

GOOGLE_CLIENT_ID_ENV = "GOOGLE_CLIENT_ID"
GOOGLE_DEFAULT_ROLE_ENV = "GOOGLE_DEFAULT_ROLE"
GOOGLE_ALLOWED_EMAILS_ENV = "GOOGLE_ALLOWED_EMAILS"
GOOGLE_ALLOWED_DOMAINS_ENV = "GOOGLE_ALLOWED_DOMAINS"

GOOGLE_DEFAULT_ROLE = "employee"


@dataclass(frozen=True)
class GoogleIdentity:
    """Verified claims from a Google ID token that survived every gate."""

    email: str
    subject: str
    email_verified: bool


class GoogleAuthError(AuthError):
    """Any Google ID-token verification failure. Details are logged, never returned."""


def _norm(value: str) -> str:
    return value.strip().lower()


def _configured_emails() -> list[str]:
    return [
        _norm(item) for item in os.getenv(GOOGLE_ALLOWED_EMAILS_ENV, "").split(",") if item.strip()
    ]


def _configured_domains() -> list[str]:
    return [
        _norm(item) for item in os.getenv(GOOGLE_ALLOWED_DOMAINS_ENV, "").split(",") if item.strip()
    ]


def is_email_allowed(email: str) -> bool:
    """Return True when the verified email is explicitly authorized to sign in.

    The email is allowed when it exactly matches an entry in
    GOOGLE_ALLOWED_EMAILS, OR when the part after "@" matches an entry in
    GOOGLE_ALLOWED_DOMAINS. Both matches are case-insensitive.

    FAIL CLOSED: when both variables are unset or empty the function returns
    False for everyone — an operator must explicitly configure at least one
    allowlist before any Google user can authenticate.
    """
    if not isinstance(email, str):
        return False
    normalized = _norm(email)
    emails = _configured_emails()
    domains = _configured_domains()
    if not emails and not domains:
        return False
    if normalized in emails:
        return True
    if "@" in normalized:
        domain = normalized.rsplit("@", 1)[1]
        if domain and domain in domains:
            return True
    return False


def default_role_for_email(email: str) -> str:
    """Map a verified, allowlisted Google email to a context-aware-guardrail role.

    Every authorized Google user currently receives a single default role
    (GOOGLE_DEFAULT_ROLE, default "employee"). This is the single place to hang
    a future email/domain -> role mapping.
    """
    configured = os.getenv(GOOGLE_DEFAULT_ROLE_ENV, "").strip()
    return configured or GOOGLE_DEFAULT_ROLE


def _verify_google_id_token(client_id: str, token: str) -> GoogleIdentity:
    """Default verification path: real Google public-key verification.

    Uses google-auth's id_token.verify_oauth2_token (cached Google certs plus
    signature, expiry, and audience checks). Imported lazily so the app stays
    importable without the provider package installed.
    """
    try:
        from google.auth.transport import requests
        from google.oauth2 import id_token
    except ImportError as exc:
        raise GoogleAuthError(
            "Google auth library (google-auth[requests]) is not installed"
        ) from exc

    info = id_token.verify_oauth2_token(token, requests.Request(), audience=client_id)
    email = info.get("email")
    if not isinstance(email, str) or not email.strip():
        raise GoogleAuthError("ID token carried no email claim")
    return GoogleIdentity(
        email=email.strip(),
        subject=info.get("sub", ""),
        email_verified=info.get("email_verified") is True,
    )


class GoogleIdTokenVerifier:
    """Server-side verifier for Google ID tokens (verify_fn injectable for tests)."""

    def __init__(
        self,
        client_id: str | None = None,
        verify_fn: Callable[[str, str], GoogleIdentity] | None = None,
    ) -> None:
        self.client_id = client_id if client_id is not None else os.getenv(GOOGLE_CLIENT_ID_ENV, "")
        self._verify_fn = verify_fn or _verify_google_id_token

    def verify_token(self, token: str) -> GoogleIdentity:
        """Verify the ID token, then enforce the identity gates. Fail closed on any error."""
        if not self.client_id.strip():
            raise AuthConfigError(
                f"{GOOGLE_CLIENT_ID_ENV} is unset or empty; cannot verify Google ID tokens."
            )
        if not isinstance(token, str) or not token.strip():
            raise GoogleAuthError("missing Google ID token")
        try:
            identity = self._verify_fn(self.client_id, token)
        except AuthConfigError:
            raise
        except AuthError:
            raise
        except Exception as exc:
            # google-auth raises its own exception types plus ValueError for
            # wrong audience / malformed tokens. Only the exception class name
            # surfaces to callers — matching core.verify_token's boundary.
            raise GoogleAuthError(f"Google ID token rejected ({type(exc).__name__})") from exc
        if not isinstance(identity, GoogleIdentity):
            raise GoogleAuthError("Google verifier returned a malformed identity")
        if not identity.email_verified:
            raise GoogleAuthError("Google email is not verified")
        if not identity.email or "@" not in identity.email:
            raise GoogleAuthError("Google identity has no verifiable email")
        return identity


def get_google_verifier(**kwargs: Any) -> GoogleIdTokenVerifier:
    """Factory mirroring the other services/*/factory.py get_*() pattern."""
    return GoogleIdTokenVerifier(**kwargs)
