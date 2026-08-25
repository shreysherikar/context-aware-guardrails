"""
Output guardrail factory (services/output_guardrail/factory).

Picks the OutputGuardrail implementation from the OUTPUT_GUARDRAIL_PROVIDER
environment variable, mirroring the risk-classifier and generation-gateway
factories. Unset/empty means the output-guardrail stage is skipped entirely
(ALLOW responses are returned without post-generation inspection); "groq" is
the implemented provider. Unknown values fail loudly at startup.
"""

import os

from services.output_guardrail.guardrail import OutputGuardrail


def get_output_guardrail() -> OutputGuardrail | None:
    """Return the configured output guardrail, or None when none is configured."""
    provider = os.getenv("OUTPUT_GUARDRAIL_PROVIDER", "").strip().lower()
    if not provider:
        return None
    if provider == "groq":
        # Imported here so importing the factory never constructs a Groq
        # client until an output guardrail is actually needed.
        from services.output_guardrail.groq_guardrail import GroqOutputGuardrail

        return GroqOutputGuardrail()
    raise ValueError(
        f"Unsupported OUTPUT_GUARDRAIL_PROVIDER={provider!r}; expected 'groq' or unset."
    )
