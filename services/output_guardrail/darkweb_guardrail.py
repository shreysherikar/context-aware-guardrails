"""Deterministic dark-web output guardrail — always-on cyber-safety layer."""

from __future__ import annotations

from domain.models import OutputAssessment
from services.cyber_safety.darkweb import process_llm_output


class DarkWebOutputGuardrail:
    """Inspect LLM output for actionable dark-web access guidance."""

    async def check(self, prompt: str, generated_text: str) -> OutputAssessment:
        result = process_llm_output(prompt, generated_text)
        assessment = result.assessment

        if result.flagged or result.original_blocked:
            return OutputAssessment(
                flagged=True,
                blocked=True,
                safe_text=result.text,
                rewrite_applied=result.rewrite_applied,
                reasoning="; ".join(assessment.reasons) if assessment else "Dark-web policy violation",
                confidence=assessment.confidence if assessment else 0.9,
                unverified_claims=assessment.categories if assessment else ["CYBER_SAFETY"],
            )

        if result.rewrite_applied:
            return OutputAssessment(
                flagged=False,
                blocked=False,
                safe_text=result.text,
                rewrite_applied=True,
                reasoning="Output rewritten to remove operational dark-web guidance",
                confidence=assessment.confidence if assessment else 0.85,
            )

        return OutputAssessment(
            flagged=False,
            reasoning="No actionable dark-web access content detected",
            confidence=assessment.confidence if assessment else 0.8,
        )
