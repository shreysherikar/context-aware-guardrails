"""
Output guardrail factory (services/output_guardrail/factory).

Always includes the deterministic DarkWebOutputGuardrail layer.
Optional Groq provider is chained when OUTPUT_GUARDRAIL_PROVIDER=groq.
"""

import os

from services.output_guardrail.composite import CompositeOutputGuardrail
from services.output_guardrail.darkweb_guardrail import DarkWebOutputGuardrail
from services.output_guardrail.guardrail import OutputGuardrail
from services.output_guardrail.multimodal_guardrail import MultimodalOutputGuardrail


def get_output_guardrail() -> OutputGuardrail:
    """Return the configured output guardrail stack (dark-web + multimodal always on)."""
    layers: list[OutputGuardrail] = [
        DarkWebOutputGuardrail(),
        MultimodalOutputGuardrail(),
    ]
    provider = os.getenv("OUTPUT_GUARDRAIL_PROVIDER", "").strip().lower()
    if provider == "groq":
        from services.output_guardrail.groq_guardrail import GroqOutputGuardrail

        layers.append(GroqOutputGuardrail())
    elif provider == "nemo":
        from services.nemo_guardrail.factory import get_nemo_output_guardrail

        nemo = get_nemo_output_guardrail()
        if nemo is None:
            raise ValueError(
                "OUTPUT_GUARDRAIL_PROVIDER=nemo requires NEMO_GUARDRAILS_ENABLED=true "
                "and output in NEMO_GUARDRAILS_MODE."
            )
        layers.append(nemo)
    elif provider:
        raise ValueError(
            f"Unsupported OUTPUT_GUARDRAIL_PROVIDER={provider!r}; "
            "expected 'groq', 'nemo', or unset."
        )

    # Defense-in-depth: NeMo output rail can run alongside other providers.
    if provider != "nemo":
        from services.nemo_guardrail.factory import get_nemo_output_guardrail

        nemo = get_nemo_output_guardrail()
        if nemo is not None:
            layers.append(nemo)

    return CompositeOutputGuardrail(*layers)
