"""NeMo Guardrails factory — lazy singleton wiring."""

from __future__ import annotations

import os
from functools import lru_cache

from services.nemo_guardrail.client import NeMoGuardrailsClient, build_nemo_client
from services.nemo_guardrail.dialog_rail import NeMoDialogRail
from services.nemo_guardrail.input_rail import NeMoInputRail


def is_nemo_enabled() -> bool:
    """Return True when NeMo defense-in-depth rails are active."""
    flag = os.getenv("NEMO_GUARDRAILS_ENABLED", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _enabled_modes() -> set[str]:
    raw = os.getenv("NEMO_GUARDRAILS_MODE", "input,output,dialog").strip().lower()
    return {part.strip() for part in raw.split(",") if part.strip()}


@lru_cache(maxsize=1)
def _client() -> NeMoGuardrailsClient:
    return build_nemo_client()


def get_nemo_input_rail() -> NeMoInputRail | None:
    if not is_nemo_enabled() or "input" not in _enabled_modes():
        return None
    return NeMoInputRail(_client())


def get_nemo_dialog_rail() -> NeMoDialogRail | None:
    if not is_nemo_enabled() or "dialog" not in _enabled_modes():
        return None
    return NeMoDialogRail(_client())


def get_nemo_output_guardrail():
    """Return NeMo output guardrail when output mode is enabled."""
    if not is_nemo_enabled() or "output" not in _enabled_modes():
        return None
    from services.nemo_guardrail.output_rail import NeMoOutputGuardrail

    return NeMoOutputGuardrail(_client())
