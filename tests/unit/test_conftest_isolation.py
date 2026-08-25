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
