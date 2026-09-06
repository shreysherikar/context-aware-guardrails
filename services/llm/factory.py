"""
Gateway factory (services/llm/factory).

Picks the LLMGateway implementation from the LLM_GENERATION_PROVIDER
environment variable. This is deliberately INDEPENDENT of the risk-classifier
provider variable (LLM_PROVIDER, read by services/risk_engine/factory.py):
which model classifies risk and which provider generates post-ALLOW responses
are separate configuration decisions.

LLM_GENERATION_PROVIDER values:
- unset/empty (default) -> Groq if GROQ_API_KEY is set (cloud secret), else None
- "groq" -> GroqLLMGateway when GROQ_API_KEY is set; otherwise no gateway
  (does not crash startup — cloud images must boot without a key in the repo)
- "ollama" -> OllamaLLMGateway only when GROQ_API_KEY is unset (local PC).
  A cloud GROQ_API_KEY always wins, because Ollama on a developer machine is
  not reachable from Render.

Unknown values fail loudly rather than silently disabling generation.
"""

import logging
import os

from services.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)


def _groq_api_key() -> str:
    return os.getenv("GROQ_API_KEY", "").strip()


def resolved_generation_provider() -> str:
    """Provider that will actually answer ALLOW-ed prompts."""
    explicit = os.getenv("LLM_GENERATION_PROVIDER", "").strip().lower()
    if explicit and explicit not in {"", "groq", "ollama", "auto"}:
        return explicit
    # Hosted deploys cannot call Ollama on someone's PC. A dashboard Groq key
    # is the answer model for every cloud user.
    if _groq_api_key():
        return "groq"
    if explicit == "ollama":
        return "ollama"
    if explicit in {"groq", "auto"}:
        return "groq"
    return ""


def get_gateway() -> LLMGateway | None:
    """Return the configured generation gateway, or None when none is configured."""
    provider = resolved_generation_provider()
    if not provider:
        return None
    if provider == "groq":
        if not _groq_api_key():
            logger.warning(
                "Groq generation requested but GROQ_API_KEY is empty; "
                "serving without a generation gateway"
            )
            return None
        # Imported here so importing the factory never constructs a Groq
        # client until a gateway is actually needed.
        from services.llm.groq_gateway import GroqLLMGateway

        return GroqLLMGateway()
    if provider == "ollama":
        from services.llm.ollama_gateway import OllamaLLMGateway

        return OllamaLLMGateway()
    raise ValueError(
        f"Unsupported LLM_GENERATION_PROVIDER={provider!r}; expected 'groq', 'ollama', or unset."
    )
