"""NVIDIA NeMo Guardrails integration — defense-in-depth layer for ContextGuard.

NeMo augments (never replaces) the existing classifier, SanitizationEngine,
policy engine, and output guardrail stack. Results are normalized into the
ContextGuard decision model; internal rail logic is never exposed to callers.
"""

from services.nemo_guardrail.factory import (
    get_nemo_dialog_rail,
    get_nemo_input_rail,
    is_nemo_enabled,
)

__all__ = [
    "get_nemo_dialog_rail",
    "get_nemo_input_rail",
    "is_nemo_enabled",
]
