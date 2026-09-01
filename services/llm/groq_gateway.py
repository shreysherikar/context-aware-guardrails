"""
Groq LLM gateway (services/llm).

Concrete LLMGateway implementation backed by Groq chat completions. Kept
minimal on purpose: it returns generated text. All configuration comes from
environment variables, matching the existing Groq classifier.

The gateway is only ever reached for ALLOW requests — the deterministic
policy engine runs before it.
"""

import logging
import os
from typing import Any

from groq import Groq

from services.llm.gateway import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"

_SYSTEM_PROMPT = "You are a helpful assistant for a pharmaceutical company."


class GroqLLMGateway:
    """Generates a helpful text response via Groq."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: Any | None = None,
    ) -> None:
        env = os.environ
        self.model = model or env.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        self.timeout = float(
            timeout if timeout is not None else env.get("GROQ_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
        )
        self._client = (
            client
            if client is not None
            else Groq(api_key=api_key or env.get("GROQ_API_KEY"), timeout=self.timeout)
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        system = request.system_prompt or _SYSTEM_PROMPT
        # NOTE: this uses the synchronous Groq client inside an async gateway
        # method, so each call briefly blocks the event loop. Acceptable at the
        # current scale; consider groq.AsyncGroq / non-blocking IO if concurrent
        # production traffic becomes relevant.
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": request.prompt},
            ],
            temperature=0.0,
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM returned an empty response")
        return LLMResponse(text=content)
