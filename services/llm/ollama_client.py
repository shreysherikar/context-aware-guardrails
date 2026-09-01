"""Shared HTTP client for the local Ollama API."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.6:latest"
DEFAULT_TIMEOUT_SECONDS = 600.0


class OllamaError(RuntimeError):
    """Raised when Ollama cannot complete a request."""


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _default_model() -> str:
    return os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)


def _timeout() -> float:
    return float(os.getenv("OLLAMA_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))


def chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float | None = None,
    format_json: bool = False,
) -> str:
    """Call Ollama /api/chat (non-streaming) and return assistant text."""
    payload: dict[str, Any] = {
        "model": model or _default_model(),
        "messages": messages,
        "stream": False,
    }
    if format_json:
        payload["format"] = "json"

    url = f"{(base_url or _base_url())}/api/chat"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout or _timeout()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.warning("Ollama HTTP error %s: %s", exc.code, detail)
        raise OllamaError(f"Ollama request failed with HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        logger.warning("Ollama connection error: %s", exc)
        raise OllamaError(
            "Cannot reach Ollama. Start it with `ollama serve` and ensure a model is pulled."
        ) from exc
    except TimeoutError as exc:
        logger.warning("Ollama request timed out")
        raise OllamaError("Ollama request timed out.") from exc

    message = data.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaError("Ollama returned an empty response.")
    return content.strip()
