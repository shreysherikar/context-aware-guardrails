"""Focused tests for the two independent provider selections.

LLM_PROVIDER selects the risk-classifier implementation
(services/risk_engine/factory.py); LLM_GENERATION_PROVIDER selects the
post-ALLOW generative gateway (services/llm/factory.py). These tests pin both
mappings and prove the two settings do not influence each other.
"""

import pytest

from services.llm.factory import get_gateway
from services.llm.groq_gateway import GroqLLMGateway
from services.llm.ollama_gateway import OllamaLLMGateway
from services.risk_engine.classifier import KeywordMockClassifier
from services.risk_engine.factory import get_classifier
from services.risk_engine.groq_classifier import GroqRiskClassifier


def _use_groq_key(monkeypatch):
    # Constructing a Groq-backed component requires an api key at client init;
    # tests never make network calls with it.
    monkeypatch.setenv("GROQ_API_KEY", "test-key")


def test_generation_provider_unset_means_no_gateway(monkeypatch):
    monkeypatch.delenv("LLM_GENERATION_PROVIDER", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert get_gateway() is None


def test_generation_provider_empty_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv("LLM_GENERATION_PROVIDER", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert get_gateway() is None


def test_groq_key_alone_enables_generation(monkeypatch):
    monkeypatch.delenv("LLM_GENERATION_PROVIDER", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    assert isinstance(get_gateway(), GroqLLMGateway)


def test_groq_provider_without_key_does_not_crash(monkeypatch):
    monkeypatch.setenv("LLM_GENERATION_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert get_gateway() is None


def test_generation_provider_groq_builds_groq_gateway(monkeypatch):
    _use_groq_key(monkeypatch)
    monkeypatch.setenv("LLM_GENERATION_PROVIDER", "groq")
    assert isinstance(get_gateway(), GroqLLMGateway)


def test_generation_provider_ollama_builds_ollama_gateway(monkeypatch):
    monkeypatch.setenv("LLM_GENERATION_PROVIDER", "ollama")
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert isinstance(get_gateway(), OllamaLLMGateway)


def test_groq_key_is_used_on_cloud_instead_of_ollama(monkeypatch):
    monkeypatch.setenv("LLM_GENERATION_PROVIDER", "ollama")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    assert isinstance(get_gateway(), GroqLLMGateway)


def test_generation_provider_unknown_fails_loudly(monkeypatch):
    monkeypatch.setenv("LLM_GENERATION_PROVIDER", "not-a-provider")
    with pytest.raises(ValueError, match="LLM_GENERATION_PROVIDER"):
        get_gateway()


def test_classifier_still_reads_llm_provider_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert isinstance(get_classifier(), KeywordMockClassifier)


def test_classifer_and_generation_providers_are_independent(monkeypatch):
    """The key decoupling guarantee: either setting can change alone."""
    _use_groq_key(monkeypatch)

    # Mock classifier + real generation gateway.
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_GENERATION_PROVIDER", "groq")
    assert isinstance(get_classifier(), KeywordMockClassifier)
    assert isinstance(get_gateway(), GroqLLMGateway)

    # Real classifier + no generation gateway (no Groq key, provider unset).
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("LLM_GENERATION_PROVIDER", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    assert isinstance(get_classifier(), GroqRiskClassifier)
    assert isinstance(get_gateway(), GroqLLMGateway)

    monkeypatch.setenv("GROQ_API_KEY", "")
    assert get_gateway() is None
