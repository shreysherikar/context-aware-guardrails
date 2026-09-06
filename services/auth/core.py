"""
Bearer-token role verification (services/auth).

Interim identity mechanism: HS256-signed JWT bearer tokens with a shared
secret from AUTH_JWT_SECRET. This is real cryptographic verification of the
role claim — not a full SSO/OIDC integration, which remains a separate open
decision.

Trust boundary (exactly, no shortcuts):

    Authorization: Bearer <JWT>
      -> verification algorithm pinned to HS256 (never read from the token)
      -> signature valid?
      -> exp present and not expired?
      -> role claim a non-empty string after stripping whitespace?
      -> verified role returned to the caller

Every failure inside that boundary raises AuthError carrying only the
exception type name; callers translate it into one generic 401 and log the
specific reason server-side. Token contents are never echoed.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

SECRET_ENV_VAR = "AUTH_JWT_SECRET"
DEV_MODE_ENV_VAR = "AUTH_DEV_MODE"
ALGORITHMS = ["HS256"]
DEFAULT_TOKEN_TTL_SECONDS = 3600


class AuthError(Exception):
    """Any token-verification failure. Details are logged, never returned."""


class AuthConfigError(RuntimeError):
    """Auth configuration is missing/invalid (operator error, not caller error)."""


def is_dev_mode_enabled() -> bool:
    """AUTH_DEV_MODE is off unless explicitly enabled ("true"/"1"/"yes")."""
    return os.getenv(DEV_MODE_ENV_VAR, "").strip().lower() in {"true", "1", "yes"}


def _get_secret() -> str:
    secret = os.getenv(SECRET_ENV_VAR, "")
    if not secret.strip():
        raise AuthConfigError(f"{SECRET_ENV_VAR} is unset or empty; cannot verify or mint tokens.")
    return secret


def ensure_startup_requirements() -> None:
    """Fail loudly at startup when the app cannot verify tokens securely.

    With AUTH_DEV_MODE disabled (the default), a missing shared secret would
    mean every authenticated request fails anyway — and worse, an operator
    might be tempted to weaken the check. Refuse to start instead.
    """
    if is_dev_mode_enabled():
        return
    secret = os.getenv(SECRET_ENV_VAR, "")
    if not secret.strip():
        raise RuntimeError(
            f"{SECRET_ENV_VAR} is unset or empty while {DEV_MODE_ENV_VAR} is "
            "disabled. Set a strong shared secret, or explicitly enable "
            f"{DEV_MODE_ENV_VAR} for local development only."
        )


def _validate_role(role: Any) -> str:
    """Role must be a non-empty string after stripping whitespace."""
    if not isinstance(role, str):
        raise AuthError("role claim must be a string")
    stripped = role.strip()
    if not stripped:
        raise AuthError("role claim must not be empty")
    return stripped


def mint_token(
    role: str,
    *,
    subject: str | None = None,
    expires_in_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
) -> str:
    """Sign an HS256 token carrying the given role and optional subject.

    This is the single minting path for every token this service issues: dev
    tokens and IdP-verified tokens alike. The optional ``subject`` claim carries
    the verified caller identity (e.g. a Google email) when it is known.
    """
    validated = _validate_role(role)
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "role": validated,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    if subject is not None:
        if not isinstance(subject, str) or not subject.strip():
            raise AuthError("subject claim must be a non-empty string")
        payload["sub"] = subject.strip()
    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def mint_dev_token(role: str, expires_in_seconds: int = DEFAULT_TOKEN_TTL_SECONDS) -> str:
    """Sign an HS256 token carrying the given role. Dev/test issuance path."""
    return mint_token(role, expires_in_seconds=expires_in_seconds)


def verify_token(token: str) -> str:
    """Verify a bearer token and return the verified role claim.

    The algorithm is pinned to HS256 — an attacker-controlled "alg" header can
    never switch the verification method (the standard JWT alg-confusion
    mitigation). Expiry and signature failures raise before the role is read.
    """
    try:
        payload = jwt.decode(
            token,
            _get_secret(),
            algorithms=ALGORITHMS,
            options={"require": ["exp"]},
        )
    except jwt.InvalidTokenError as exc:
        # Covers expired, wrong-algorithm, bad-signature, malformed and
        # missing-claim cases. Only the exception class name surfaces.
        raise AuthError(f"token rejected ({type(exc).__name__})") from exc
    return _validate_role(payload.get("role"))
