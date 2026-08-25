"""Unit tests for GroqOutputGuardrail with a stubbed Groq client.

No real network calls happen here: ``client.chat.completions.create`` is a
local stub returning canned objects shaped like the Groq SDK's ChatCompletion,
and SDK exceptions are raised directly from the stub.

check() raises on provider/parse failure; the API layer converts that into a
fail-closed flagged-for-review outcome. The model's judgment is stubbed input
— these tests verify the contract (strict schema, faithful mapping), not the
model's judgment itself.
"""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from groq import APITimeoutError, RateLimitError

from domain.models import OutputAssessment
from services.output_guardrail.groq_guardrail import (
    DEFAULT_GROQ_MODEL,
    GroqOutputGuardrail,
    _output_assessment_schema,
)

OUTPUT_ASSESSMENT_FIELDS = [
    "flagged",
    "unverified_claims",
    "reasoning",
    "confidence",
]


def _guardrail(client) -> GroqOutputGuardrail:
    return GroqOutputGuardrail(api_key="test-key", client=client)


def _run(coro):
    return asyncio.run(coro)


def _client_responding(content: str) -> tuple[SimpleNamespace, list[dict]]:
    """Stub client that records the create() kwargs and returns content."""

    calls: list[dict] = []

    def create(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, calls


def _client_raising(exc: Exception) -> SimpleNamespace:
    def create(**_kwargs: object) -> None:
        raise exc

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _timeout_error() -> APITimeoutError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return APITimeoutError(request)


def _rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return RateLimitError("rate limited", response=response, body=None)


def _assessment(**overrides: object) -> str:
    base = {
        "flagged": False,
        "unverified_claims": [],
        "reasoning": "all claims are supported by the prompt",
        "confidence": 0.9,
    }
    base.update(overrides)
    return json.dumps(base)


def test_default_model_and_timeout_config():
    guardrail = GroqOutputGuardrail(api_key="test-key")
    assert guardrail.model == DEFAULT_GROQ_MODEL
    assert guardrail.timeout == 10.0


def test_strict_schema_matches_domain_contract():
    schema = _output_assessment_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    # strict mode: every property required, and only the four domain fields
    assert schema["required"] == OUTPUT_ASSESSMENT_FIELDS
    assert set(schema["properties"]) == set(OUTPUT_ASSESSMENT_FIELDS)
    serialized = json.dumps(schema)
    assert "default" not in serialized  # no omitted default-valued fields
    assert "$ref" not in serialized and "$defs" not in serialized  # self-contained
    assert schema["properties"]["confidence"]["minimum"] == 0.0


def test_payload_requests_strict_structured_outputs():
    client, calls = _client_responding(_assessment())
    prompt = "Summarize this internal document."
    generated = "Here is the summary."
    _run(_guardrail(client).check(prompt, generated))

    payload = calls[0]
    assert payload["temperature"] == 0.0
    response_format = payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["name"] == "output_assessment"
    # both the prompt and the generated text reach the model as user content
    assert prompt in payload["messages"][1]["content"]
    assert generated in payload["messages"][1]["content"]


def test_unsupported_claim_is_flagged():
    client, _ = _client_responding(
        _assessment(
            flagged=True,
            unverified_claims=["Drug X cures the condition with zero side effects."],
            reasoning="Efficacy claim absent from the prompt.",
            confidence=0.95,
        )
    )
    result = _run(
        _guardrail(client).check(
            "Summarize this internal document.",
            "Clinical trials confirm Drug X cures the condition.",
        )
    )

    assert isinstance(result, OutputAssessment)
    assert result.flagged is True
    assert result.unverified_claims == ["Drug X cures the condition with zero side effects."]
    assert result.confidence == 0.95


def test_fully_grounded_response_passes():
    client, _ = _client_responding(
        _assessment(reasoning="Summary restates only what the prompt asked for.")
    )
    result = _run(
        _guardrail(client).check("Summarize this internal document.", "Here is the summary.")
    )

    assert result.flagged is False
    assert result.unverified_claims == []


def test_fails_closed_on_timeout():
    client = _client_raising(_timeout_error())
    with pytest.raises(APITimeoutError):
        _run(_guardrail(client).check("prompt", "generated"))


def test_fails_closed_on_rate_limit():
    client = _client_raising(_rate_limit_error())
    with pytest.raises(RateLimitError):
        _run(_guardrail(client).check("prompt", "generated"))


def test_fails_closed_on_generic_sdk_error():
    client = _client_raising(RuntimeError("connection broke"))
    with pytest.raises(RuntimeError):
        _run(_guardrail(client).check("prompt", "generated"))


def test_fails_closed_on_malformed_json_output():
    client, _ = _client_responding("this is not json")
    with pytest.raises(ValueError):
        _run(_guardrail(client).check("prompt", "generated"))


def test_fails_closed_on_schema_invalid_output():
    # confidence must be numeric; a non-numeric string violates the contract
    # and pydantic cannot coerce it.
    client, _ = _client_responding(
        json.dumps(
            {
                "flagged": True,
                "unverified_claims": [],
                "reasoning": "x",
                "confidence": "high",
            }
        )
    )
    with pytest.raises(ValueError):
        _run(_guardrail(client).check("prompt", "generated"))


def test_fails_closed_on_missing_field():
    client, _ = _client_responding(
        '{"unverified_claims": [], "reasoning": "ok", "confidence": 0.9}'
    )
    with pytest.raises(ValueError):
        _run(_guardrail(client).check("prompt", "generated"))


def test_fails_closed_on_empty_response():
    client, _ = _client_responding("")
    with pytest.raises(ValueError):
        _run(_guardrail(client).check("prompt", "generated"))


def test_fails_closed_on_no_choices():
    def create(**_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(choices=[])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(ValueError):
        _run(_guardrail(client).check("prompt", "generated"))
