"""
LLM gateway abstraction (services/llm).

The application/API layer depends on this interface, never on a provider SDK,
so a provider can be swapped later without redesigning the flow. The current
implementation is a minimal Groq gateway that returns generated text. No
multi-provider framework is built here.
"""

from typing import Protocol

from pydantic import BaseModel


class LLMRequest(BaseModel):
    """Minimal input the gateway needs to generate a response."""

    prompt: str
    system_prompt: str | None = None
    # The downstream model has no context beyond the prompt in the current
    # implementation. Additional context (conversation history, retrieved
    # evidence) is a separate future decision.


class LLMResponse(BaseModel):
    """Minimal generated output plus only what the current application needs."""

    text: str


class LLMGateway(Protocol):
    """Callable interface used by the API to generate a response."""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response for an allowed request. Raises on provider failure."""
        ...
