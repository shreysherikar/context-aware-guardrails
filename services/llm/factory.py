"""
Gateway factory (services/llm/factory).

Picks the LLMGateway implementation from the LLM_GENERATION_PROVIDER
environment variable. This is deliberately INDEPENDENT of the risk-classifier
provider variable (LLM_PROVIDER, read by services/risk_engine/factory.py):
which model classifies risk and which provider generates post-ALLOW responses
are separate configuration decisions.

LLM_GENERATION_PROVIDER values:
- unset/empty (default) -> None: no generative LLM wired; ALLOW responses
  return a null response field.
- "groq" -> GroqLLMGateway.

Unknown values fail loudly rather than silently disabling generation.
"""

import os

from services.llm.gateway import LLMGateway


def get_gateway() -> LLMGateway | None:
    """Return the configured generation gateway, or None when none is configured."""
    provider = os.getenv("LLM_GENERATION_PROVIDER", "").strip().lower()
    if not provider:
        return None
    if provider == "groq":
        # Imported here so importing the factory never constructs a Groq
        # client until a gateway is actually needed.
        from services.llm.groq_gateway import GroqLLMGateway

        return GroqLLMGateway()
    raise ValueError(f"Unsupported LLM_GENERATION_PROVIDER={provider!r}; expected 'groq' or unset.")
