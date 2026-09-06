"""Email/password sign-in against AUTH_PASSWORD_USERS.

Entries are comma-separated ``email:password:role`` triples. Comparison is
constant-time. An empty/unconfigured list authenticates nobody (fail closed).
"""

from __future__ import annotations

import hmac
import os
from typing import NamedTuple

from services.auth.core import AuthError, is_dev_mode_enabled

PASSWORD_USERS_ENV_VAR = "AUTH_PASSWORD_USERS"
DUMMY_LOGIN_ENV_VAR = "AUTH_DUMMY_LOGIN"

DUMMY_EMAIL = "demo@contextguard.local"
DUMMY_PASSWORD = "demo"
DUMMY_ROLE = "clinician"

# Local desktop/phone demo accounts. Password matches the role name.
DEFAULT_DESKTOP_USERS = (
    f"{DUMMY_EMAIL}:{DUMMY_PASSWORD}:{DUMMY_ROLE},"
    "clinician@contextguard.local:clinician:clinician,"
    "admin@contextguard.local:admin:admin,"
    "marketing@contextguard.local:marketing:marketing,"
    "employee@contextguard.local:employee:employee"
)


class PasswordIdentity(NamedTuple):
    email: str
    role: str


def _norm_email(email: str) -> str:
    return email.strip().lower()


def dummy_login_enabled() -> bool:
    """AUTH_DUMMY_LOGIN or AUTH_DEV_MODE unlocks the built-in demo account."""
    flag = os.getenv(DUMMY_LOGIN_ENV_VAR, "").strip().lower()
    if flag in {"true", "1", "yes"}:
        return True
    return is_dev_mode_enabled()


def _parse_users() -> dict[str, tuple[str, str]]:
    """email -> (password, role). Last duplicate email wins."""
    raw = os.getenv(PASSWORD_USERS_ENV_VAR, "")
    users: dict[str, tuple[str, str]] = {}
    for chunk in raw.split(","):
        entry = chunk.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) != 3:
            continue
        email, password, role = (part.strip() for part in parts)
        if not email or "@" not in email or not password or not role:
            continue
        users[_norm_email(email)] = (password, role)
    if dummy_login_enabled():
        users[DUMMY_EMAIL] = (DUMMY_PASSWORD, DUMMY_ROLE)
    return users


def _passwords_match(stored: str, submitted: str) -> bool:
    left = stored.encode("utf-8")
    right = submitted.encode("utf-8")
    size = max(len(left), len(right), 1)
    padded_ok = hmac.compare_digest(left.ljust(size, b"\0"), right.ljust(size, b"\0"))
    return padded_ok and len(left) == len(right)


def authenticate_password(email: str, password: str) -> PasswordIdentity:
    """Return the identity for a matching email/password, or raise AuthError."""
    if not isinstance(email, str) or not isinstance(password, str):
        raise AuthError("invalid credentials")
    normalized = _norm_email(email)
    users = _parse_users()
    stored = users.get(normalized)
    expected = stored[0] if stored else "missing-password"
    if not _passwords_match(expected, password) or stored is None:
        raise AuthError("invalid credentials")
    return PasswordIdentity(email=normalized, role=stored[1])
