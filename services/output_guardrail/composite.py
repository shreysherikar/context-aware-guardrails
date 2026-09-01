"""Composite output guardrail — chains deterministic layers with optional LLM guard."""

from __future__ import annotations

from domain.models import OutputAssessment
from services.output_guardrail.guardrail import OutputGuardrail


class CompositeOutputGuardrail:
    """Run multiple output guardrails in sequence (fail-closed)."""

    def __init__(self, *guardrails: OutputGuardrail) -> None:
        self._guardrails = guardrails

    async def check(self, prompt: str, generated_text: str) -> OutputAssessment:
        current_text = generated_text
        last: OutputAssessment | None = None

        for guardrail in self._guardrails:
            assessment = await guardrail.check(prompt, current_text)
            last = assessment
            if assessment.safe_text:
                current_text = assessment.safe_text
            if assessment.flagged or assessment.blocked:
                return assessment.model_copy(update={"safe_text": current_text})

        return last or OutputAssessment(flagged=False, reasoning="No guardrails configured")
