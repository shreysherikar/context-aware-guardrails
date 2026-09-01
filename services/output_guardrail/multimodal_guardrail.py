"""Multimodal output guardrail — inspect LLM output for reconstructed untrusted content."""

from __future__ import annotations

from domain.models import OutputAssessment
from services.multimodal.rewrite import process_multimodal_text


class MultimodalOutputGuardrail:
    """Detect operational instructions re-emerged in LLM output."""

    async def check(self, prompt: str, generated_text: str) -> OutputAssessment:
        result = process_multimodal_text(generated_text, source="image", is_output=True)

        if result.blocked:
            return OutputAssessment(
                flagged=True,
                blocked=True,
                safe_text=result.text,
                rewrite_applied=result.rewrite_applied,
                reasoning="Multimodal output contained actionable untrusted instructions",
                confidence=0.9,
                unverified_claims=result.assessment.categories if result.assessment else [],
            )

        if result.rewrite_applied:
            return OutputAssessment(
                flagged=False,
                safe_text=result.text,
                rewrite_applied=True,
                reasoning="Output rewritten to remove untrusted multimodal instructions",
                confidence=0.85,
            )

        return OutputAssessment(
            flagged=False,
            reasoning="No untrusted multimodal instructions in output",
            confidence=0.8,
        )
