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

Audit isolation: since policy decisions can now depend on conversation history
(trajectory engine reads prior audit events), every test gets its own fresh
AUDIT_DB_PATH. This keeps the suite deterministic — no test can inherit
history written by another test or by a previous run against the repo's
persistent audit.db.
"""

import os

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("LLM_GENERATION_PROVIDER", "")
os.environ.setdefault("OUTPUT_GUARDRAIL_PROVIDER", "")
os.environ.setdefault("CLAIM_VERIFICATION_PROVIDER", "")
os.environ.setdefault("OPTICAL_OCR_PROVIDER", "mock")

# Auth bootstrap: dev mode off (safe default), test signing secret on. Forced
# (not setdefault) for DEV_MODE so a local .env cannot flip it on and change
# which endpoints exist during a test run. The secret is >=32 bytes so HMAC-SHA256
# signing does not emit PyJWT InsecureKeyLengthWarning noise across the suite.
os.environ["AUTH_DEV_MODE"] = "false"
os.environ.setdefault("AUTH_JWT_SECRET", "unit-test-signing-secret-0123456789abcdef")

import pytest  # noqa: E402

from services.auth import mint_dev_token  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_audit_db(tmp_path, monkeypatch):
    """Give every test a fresh, isolated audit database.

    Policy decisions can depend on conversation history (trajectory engine
    reads prior audit events), so sharing the repo's persistent audit.db between
    tests or runs would make outcomes order- and state-dependent. This fixture
    points AUDIT_DB_PATH at a per-test temp file before each test and restores
    the environment afterwards. Tests that explicitly set AUDIT_DB_PATH
    themselves (e.g. migration tests) still override it within the test body.
    """
    db_path = tmp_path / "audit.db"
    monkeypatch.setenv("AUDIT_DB_PATH", str(db_path))
    return db_path


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
