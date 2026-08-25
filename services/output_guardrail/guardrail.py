"""
Output guardrail abstraction (services/output_guardrail).

Assesses the generated LLM response for unverified/unsupported claims BEFORE
it reaches the employee. The application/API layer depends on this interface,
never on a provider SDK, so the implementation is swappable the same way
RiskClassifier and LLMGateway are. Following the documented layering, this
module depends on domain/ only.
"""

from typing import Protocol

from domain.models import OutputAssessment


class OutputGuardrail(Protocol):
    """Inspect a generated response against the original prompt."""

    async def check(self, prompt: str, generated_text: str) -> OutputAssessment:
        """Assess whether generated_text contains claims not grounded in prompt.

        Raises on provider/parse failure. The API layer treats that as
        fail-closed and routes the response to flagged-for-review rather than
        returning it as a normal ALLOW success.
        """
        ...
