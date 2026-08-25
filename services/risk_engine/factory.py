"""
Classifier factory — picks the RiskClassifier implementation from config.

LLM_PROVIDER values:
- "mock" (default, also when unset) -> KeywordMockClassifier, zero network.
- "groq" -> GroqRiskClassifier (real LLM-backed).

An unknown provider is a boot-time configuration error: the API must not
silently fall back to a mock classifier in an environment that asked for a
real one, so raise loudly instead of guessing.
"""

import os

from services.risk_engine.classifier import KeywordMockClassifier, RiskClassifier
from services.risk_engine.groq_classifier import GroqRiskClassifier


class UnknownProviderError(ValueError):
    pass


def get_classifier() -> RiskClassifier:
    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    if provider == "mock":
        return KeywordMockClassifier()
    if provider == "groq":
        return GroqRiskClassifier()
    raise UnknownProviderError(f"Unknown LLM_PROVIDER={provider!r}; expected 'mock' or 'groq'.")
