"""
Test bootstrap.

Guarantees tests run fully offline regardless of a developer's local .env.
The application (apps/api/main.py) calls load_dotenv(), which would otherwise
honor a local .env with real provider config — LLM_PROVIDER=groq (risk
classifier), LLM_GENERATION_PROVIDER=groq (post-ALLOW generation) and/or
OUTPUT_GUARDRAIL_PROVIDER=groq (post-generation output guardrail) — and
construct real Groq clients. Tests must never make network calls.

All three provider variables are forced off here with setdefault BEFORE any
app import: the risk classifier falls back to the offline KeywordMockClassifier,
no generation gateway is wired (ALLOW responses return a null response), and
no output guardrail is wired (post-ALLOW responses are not inspected in tests
unless a test explicitly injects a fake). load_dotenv() does not override
existing environment variables, so these values win regardless of what .env
contains.

Auth: AUTH_DEV_MODE stays false (its safe default, forced here for
determinism), so /auth/dev-token answers 404 in the default suite. A test-only
signing secret is provided so apps/api/main.py can start; tests obtain valid
Authorization headers from the `make_auth_headers` fixture, which mints tokens
directly through services/auth — never over HTTP.
"""

import os

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("LLM_GENERATION_PROVIDER", "")
os.environ.setdefault("OUTPUT_GUARDRAIL_PROVIDER", "")

# Auth bootstrap: dev mode off (safe default), test signing secret on. Forced
# (not setdefault) for DEV_MODE so a local .env cannot flip it on and change
# which endpoints exist during a test run.
os.environ["AUTH_DEV_MODE"] = "false"
os.environ.setdefault("AUTH_JWT_SECRET", "unit-test-signing-secret")

import pytest  # noqa: E402

from services.auth import mint_dev_token  # noqa: E402


@pytest.fixture
def make_auth_headers():
    """Return a factory minting Authorization headers for a given role."""

    def _make(role: str = "researcher") -> dict[str, str]:
        return {"Authorization": f"Bearer {mint_dev_token(role)}"}

    return _make


@pytest.fixture
def auth_headers(make_auth_headers):
    """Default researcher headers, ready to pass to any client.post call."""
    return make_auth_headers("researcher")
