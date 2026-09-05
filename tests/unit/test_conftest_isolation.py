"""Regression guard for test isolation in tests/conftest.py.

tests/conftest.py must force both provider variables off before any app import
so the whole test process runs offline, regardless of a developer's local
.env. If that bootstrap is later edited such that one of the variables is no
longer defended, these tests fail — a test run would otherwise silently make a
live Groq call when a local .env enables a real provider.
"""

import os


def test_llm_generation_provider_is_forced_off_in_test_process():
    # Empty string = no generation gateway wired. A real .env may set groq;
    # conftest must override that for tests (setdefault before app import).
    assert os.environ.get("LLM_GENERATION_PROVIDER", "").strip().lower() == ""


def test_llm_provider_falls_back_to_mock_in_test_process():
    # The default (offline) classifier must be used; a real .env may set groq
    # and conftest must override that for tests without changing the app's
    # mock-when-unset default.
    assert os.environ.get("LLM_PROVIDER", "").strip().lower() == "mock"


def test_output_guardrail_provider_is_forced_off_in_test_process():
    # Empty string = no output guardrail wired. A real .env may set groq;
    # conftest must override that for tests (setdefault before app import).
    assert os.environ.get("OUTPUT_GUARDRAIL_PROVIDER", "").strip().lower() == ""


def test_optical_ocr_provider_defaults_to_mock_in_test_process():
    # Optical OCR must stay offline in CI; a local .env may set tesseract.
    assert os.environ.get("OPTICAL_OCR_PROVIDER", "").strip().lower() == "mock"


def test_allowed_origins_is_forced_in_test_process():
    # CORS tests assert on exactly this allowlist; a local .env with
    # ALLOWED_ORIGINS set could otherwise change middleware behaviour mid-suite
    # (or worse, hide a failure to restrict cross-origin access).
    assert os.environ.get("ALLOWED_ORIGINS", "").strip() == (
        "https://d123abc.cloudfront.net,http://localhost:5173"
    )


def test_serve_static_frontend_is_forced_true_in_test_process():
    # The static-mount gate defaults to off in real deployments; conftest must
    # override that so the existing web_ui static-mount coverage stays active.
    assert os.environ.get("SERVE_STATIC_FRONTEND", "").strip().lower() == "true"
