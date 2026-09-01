"""NeMo Guardrails client — wraps the SDK with timeout and fail-closed semantics."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Protocol

from services.nemo_guardrail.models import NeMoRailOutcome
from services.nemo_guardrail.normalizer import normalize_input_status, normalize_output_status

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config"


class NeMoRailsBackend(Protocol):
    """Testable backend contract for NeMo rail checks."""

    async def check_input(self, text: str) -> NeMoRailOutcome: ...

    async def check_output(self, prompt: str, generated_text: str) -> NeMoRailOutcome: ...

    async def check_dialog(self, messages: list[dict[str, str]]) -> NeMoRailOutcome: ...


class LiveNeMoBackend:
    """Production backend using the nemoguardrails SDK."""

    def __init__(
        self,
        config_path: Path,
        timeout: float,
    ) -> None:
        self._config_path = config_path
        self._timeout = timeout
        self._rails: Any | None = None

    def _ensure_rails(self) -> Any:
        if self._rails is not None:
            return self._rails
        try:
            from nemoguardrails import LLMRails, RailsConfig
        except ImportError as exc:
            raise RuntimeError(
                "nemoguardrails is not installed. "
                "Install with: pip install 'context-aware-guardrail[nemo]'"
            ) from exc

        config = RailsConfig.from_path(str(self._config_path))
        self._rails = LLMRails(config)
        return self._rails

    async def _run_check(
        self,
        messages: list[dict[str, str]],
        *,
        rail_types: list[Any] | None,
        original: str,
        normalizer: Any,
    ) -> NeMoRailOutcome:
        rails = self._ensure_rails()
        try:
            from nemoguardrails.rails.llm.options import RailType
        except ImportError:
            RailType = None  # type: ignore[misc, assignment]

        try:
            coro = rails.check_async(messages, rail_types=rail_types)
            result = await asyncio.wait_for(coro, timeout=self._timeout)
            status = getattr(result.status, "value", str(result.status))
            return normalizer(
                status=status,
                content=getattr(result, "content", original) or original,
                original=original,
            )
        except TimeoutError:
            logger.warning("NeMo rail check timed out; failing closed", exc_info=True)
            return normalizer(original=original, status="", content=original, fail_closed=True)
        except Exception:
            logger.warning("NeMo rail check failed; failing closed", exc_info=True)
            return normalizer(original=original, status="", content=original, fail_closed=True)

    async def check_input(self, text: str) -> NeMoRailOutcome:
        from nemoguardrails.rails.llm.options import RailType

        return await self._run_check(
            [{"role": "user", "content": text}],
            rail_types=[RailType.INPUT],
            original=text,
            normalizer=normalize_input_status,
        )

    async def check_output(self, prompt: str, generated_text: str) -> NeMoRailOutcome:
        from nemoguardrails.rails.llm.options import RailType

        return await self._run_check(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": generated_text},
            ],
            rail_types=[RailType.OUTPUT],
            original=generated_text,
            normalizer=normalize_output_status,
        )

    async def check_dialog(self, messages: list[dict[str, str]]) -> NeMoRailOutcome:
        """Run input rails against the latest user turn in conversation context."""
        user_messages = [m for m in messages if m.get("role") == "user"]
        original = user_messages[-1]["content"] if user_messages else ""
        return await self._run_check(
            messages,
            rail_types=None,
            original=original,
            normalizer=normalize_input_status,
        )


class NeMoGuardrailsClient:
    """Facade over a NeMoRailsBackend with sync helpers for classifier path."""

    def __init__(self, backend: NeMoRailsBackend) -> None:
        self._backend = backend

    async def check_input_async(self, text: str) -> NeMoRailOutcome:
        return await self._backend.check_input(text)

    async def check_output_async(self, prompt: str, generated_text: str) -> NeMoRailOutcome:
        return await self._backend.check_output(prompt, generated_text)

    async def check_dialog_async(self, messages: list[dict[str, str]]) -> NeMoRailOutcome:
        return await self._backend.check_dialog(messages)

    def check_input_sync(self, text: str) -> NeMoRailOutcome:
        """Run input rail from synchronous classifier context."""
        return asyncio.run(self.check_input_async(text))


def build_nemo_client() -> NeMoGuardrailsClient:
    config_path = Path(
        os.getenv("NEMO_GUARDRAILS_CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
    ).resolve()
    timeout = float(os.getenv("NEMO_GUARDRAILS_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
    backend = LiveNeMoBackend(config_path=config_path, timeout=timeout)
    return NeMoGuardrailsClient(backend)
