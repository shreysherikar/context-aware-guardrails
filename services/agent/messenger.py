"""Compose conversational agent messages from safe guardrail metadata."""

from __future__ import annotations

import json
import logging
import os

from domain.enums import PolicyAction
from services.agent.feedback import compose_deterministic_message
from services.agent.models import AgentCorrection, AgentIssue
from services.agent.persona import PHARMA_ASSISTANT_SYSTEM
from services.llm.gateway import LLMGateway
from services.llm.ollama_client import OllamaError, chat

logger = logging.getLogger(__name__)

_FEEDBACK_SYSTEM = PHARMA_ASSISTANT_SYSTEM + """

When a request cannot proceed as written, explain the issue like a helpful colleague:
- Say what is ambiguous or risky in plain language (HCP targeting, PHI, off-label, fair balance)
- Ask specific clarification questions if provided
- Offer a safer rewrite the user can copy
- Do NOT answer the original risky question when action is BLOCK or REVIEW
- When action is ALLOW and an approved answer is provided, you may return only the answer"""


def _use_llm_messenger() -> bool:
    return os.getenv("AGENT_LLM_FEEDBACK", "true").strip().lower() in {"true", "1", "yes"}


async def compose_agent_message(
    *,
    action: PolicyAction,
    issues: list[AgentIssue],
    corrections: list[AgentCorrection],
    answer: str | None = None,
    sanitized_text: str | None = None,
    output_flagged: bool = False,
    input_type: str = "text",
    gateway: LLMGateway | None = None,
    clarification_questions: list[str] | None = None,
    suggested_rewrite: str | None = None,
) -> str:
    """Return a user-facing message; uses local LLM when configured."""
    fallback = compose_deterministic_message(
        action=action,
        issues=issues,
        corrections=corrections,
        answer=answer,
        sanitized_text=sanitized_text,
        output_flagged=output_flagged,
        clarification_questions=clarification_questions,
        suggested_rewrite=suggested_rewrite,
    )

    if action == PolicyAction.ALLOW and answer and not output_flagged:
        return answer

    # Risky / ambiguous paths only — avoids a second slow LLM call on every normal chat.
    if action == PolicyAction.ALLOW:
        return fallback

    if not _use_llm_messenger():
        return fallback

    provider = os.getenv("LLM_GENERATION_PROVIDER", "").strip().lower()
    context = {
        "action": action.value,
        "input_type": input_type,
        "issues": [i.model_dump() for i in issues],
        "corrections": [c.model_dump() for c in corrections],
        "clarification_questions": clarification_questions or [],
        "suggested_rewrite": suggested_rewrite,
        "sanitized_text": sanitized_text,
        "has_answer": bool(answer) and not output_flagged,
        "output_flagged": output_flagged,
    }

    user_payload = json.dumps(context, indent=2)
    if answer and not output_flagged and action != PolicyAction.ALLOW:
        user_payload += f"\n\nApproved answer to include:\n{answer}"

    try:
        if provider == "ollama":
            return chat(
                [
                    {"role": "system", "content": _FEEDBACK_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            "Respond to the user based on this guardrail outcome. "
                            "Sound like a normal internal pharma assistant, not a security tool.\n\n"
                            + user_payload
                        ),
                    },
                ]
            )
        if provider == "groq" and gateway is not None:
            from services.llm.gateway import LLMRequest

            response = await gateway.generate(
                LLMRequest(
                    prompt=_FEEDBACK_SYSTEM
                    + "\n\nOutcome JSON:\n"
                    + user_payload
                    + "\n\nWrite your reply to the user."
                )
            )
            return response.text
    except (OllamaError, Exception):  # noqa: BLE001
        logger.exception("Agent feedback LLM failed; using deterministic message")

    return fallback
