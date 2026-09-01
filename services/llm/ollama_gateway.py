"""Ollama LLM gateway for local post-policy generation."""

from __future__ import annotations

import logging

from services.agent.persona import PHARMA_ASSISTANT_SYSTEM
from services.llm.gateway import LLMRequest, LLMResponse
from services.llm.ollama_client import OllamaError, chat

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = PHARMA_ASSISTANT_SYSTEM


class OllamaLLMGateway:
    """Generates text via a local Ollama model."""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        system = request.system_prompt or _SYSTEM_PROMPT
        try:
            text = chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": request.prompt},
                ]
            )
        except OllamaError:
            logger.exception("Ollama generation failed")
            raise
        return LLMResponse(text=text)
