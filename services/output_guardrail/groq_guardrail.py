"""
Groq-backed output guardrail (services/output_guardrail).

Concrete OutputGuardrail implementation that uses Groq chat completions with
Structured Outputs (response_format {type: json_schema, strict: true}) to keep
the model emitting OutputAssessment-shaped JSON, mirroring the pattern proven
in services/risk_engine/groq_classifier.py. The strict-schema builder is
replicated here (not shared) so that module's tested behavior is untouched.

Grounding is prompt-only: "unverified" means a claim in generated_text is not
supported by what is actually in the prompt. There is no approved-source or
RAG store yet — building one is out of scope and tracked as a separate open
decision.

check() raises on provider/parse failure (timeout, error, malformed or
schema-invalid output); the API layer fails closed and routes to
flagged-for-review rather than returning the response.
"""

import copy
import json
import logging
import os
from typing import Any

from groq import Groq

from domain.models import OutputAssessment

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"

_SYSTEM_PROMPT = """You are the output guardrail of a guardrail system for a \
pharmaceutical company. Your only job is to check whether claims in a \
model-generated response are supported by the original user prompt.

You compare two inputs:
- "prompt": the original (untrusted) user request.
- "generated_text": the model's response to that prompt.

For this milestone, a claim is "unverified" only if there is nothing in the \
prompt that supports it. Treat the prompt as the sole source of grounding; do \
not assume external or general knowledge. In particular, flag clinical, \
efficacy, safety, or comparative claims (for example "this drug cures X" or \
"this treatment is proven effective") when the prompt does not contain any \
supporting statement for them.

Output fields:
- flagged: true if generated_text contains at least one unverified claim.
- unverified_claims: the specific unsupported claims (empty list when none).
- reasoning: one or two sentences justifying the assessment.
- confidence: your confidence in this assessment, 0.0 to 1.0.

You never decide an action — you only report structured metadata. Respond \
with valid JSON matching the provided schema exactly. No prose around it."""


def _output_assessment_schema() -> dict[str, Any]:
    """Strict-mode JSON schema for OutputAssessment, built from pydantic.

    Mirrors the classifier's schema builder: Groq strict mode requires every
    property in the top-level "required" array and root
    "additionalProperties": false, and does not accept Optional/default-valued
    fields being omitted, so defaults are dropped and all four fields become
    required.
    """
    schema = OutputAssessment.model_json_schema()

    defs = schema.get("$defs", {})

    def _strip_defaults(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: _strip_defaults(v) for k, v in value.items() if k != "default"}
        if isinstance(value, list):
            return [_strip_defaults(v) for v in value]
        return value

    def _dereference(value: Any) -> Any:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if ref and ref.startswith("#/$defs/") and ref.rsplit("/", 1)[-1] in defs:
                return _strip_defaults(copy.deepcopy(defs[ref.rsplit("/", 1)[-1]]))
            return {k: _dereference(v) for k, v in value.items() if k != "$ref"}
        if isinstance(value, list):
            return [_dereference(v) for v in value]
        return value

    cleaned = _dereference(_strip_defaults(schema))
    cleaned.pop("$defs", None)
    cleaned["additionalProperties"] = False
    cleaned["required"] = list(OutputAssessment.model_fields.keys())
    for key in ("title", "description"):
        cleaned.pop(key, None)
    return cleaned


class GroqOutputGuardrail:
    """Output guardrail backed by a Groq chat completion with Structured Outputs."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: Any | None = None,
    ) -> None:
        env = os.environ
        self.model = model or env.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        self.timeout = float(
            timeout if timeout is not None else env.get("GROQ_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
        )
        self._json_schema = _output_assessment_schema()
        self._client = (
            client
            if client is not None
            else Groq(api_key=api_key or env.get("GROQ_API_KEY"), timeout=self.timeout)
        )

    async def check(self, prompt: str, generated_text: str) -> OutputAssessment:
        # NOTE: uses the synchronous Groq client inside an async method, so each
        # call briefly blocks the event loop — acceptable at the current scale.
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({"prompt": prompt, "generated_text": generated_text}),
                },
            ],
            temperature=0.0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "output_assessment",
                    "strict": True,
                    "schema": self._json_schema,
                },
            },
        )
        return self._parse_response(response)

    def _parse_response(self, response: Any) -> OutputAssessment:
        """Map the structured Groq payload onto OutputAssessment.

        Raises on anything that cannot be treated as a valid OutputAssessment;
        the API layer converts that into a fail-closed flagged-for-review
        outcome.
        """
        choices = getattr(response, "choices", None)
        if not choices:
            raise ValueError("Groq output guardrail response contained no choices")
        content = getattr(choices[0].message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Groq output guardrail returned missing or empty content")
        data = json.loads(content)  # strict-mode output should always parse
        return OutputAssessment.model_validate(data)
