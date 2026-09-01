"""NeMo output rail — post-generation defense-in-depth layer."""

from __future__ import annotations

from domain.models import OutputAssessment
from services.nemo_guardrail.client import NeMoGuardrailsClient
from services.nemo_guardrail.normalizer import outcome_to_output_assessment


class NeMoOutputGuardrail:
    """OutputGuardrail implementation backed by NeMo output rails.

    Raises on indeterminate/fail-closed outcomes so the API layer routes to
    REVIEW rather than returning unverified generated text.
    """

    def __init__(self, client: NeMoGuardrailsClient) -> None:
        self._client = client

    async def check(self, prompt: str, generated_text: str) -> OutputAssessment:
        outcome = await self._client.check_output_async(prompt, generated_text)
        return outcome_to_output_assessment(outcome)
