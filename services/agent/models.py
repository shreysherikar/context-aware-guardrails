"""Agent response models — user-facing feedback on guardrail outcomes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.enums import PolicyAction


class AgentIssue(BaseModel):
    """One policy or risk issue detected in the user's request."""

    code: str
    title: str
    description: str
    severity: str = "medium"
    why: str | None = None


class PromptHighlight(BaseModel):
    """Span in the user's prompt that triggered a guardrail concern."""

    start: int
    end: int
    text: str
    code: str
    reason: str
    severity: str = "medium"


class AgentCorrection(BaseModel):
    """Actionable guidance on how to fix or resubmit safely."""

    title: str
    description: str
    example: str | None = None


class AgentActivation(BaseModel):
    """One specialist agent that participated in handling the request."""

    id: str
    name: str
    role: str = "specialist"


class AgentChatResponse(BaseModel):
    """Full agent reply: guardrail outcome + explanation + optional LLM answer."""

    conversation_id: str
    action: PolicyAction
    message: str
    issues: list[AgentIssue] = Field(default_factory=list)
    corrections: list[AgentCorrection] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    suggested_rewrite: str | None = None
    prompt_class: str | None = None
    answer: str | None = None
    sanitized_text: str | None = None
    input_type: str = "text"
    policy_id: str | None = None
    blocked: bool = False
    review_required: bool = False
    web_search_used: bool = False
    web_sources: list[dict[str, str]] = Field(default_factory=list)
    active_agents: list[AgentActivation] = Field(default_factory=list)
    primary_agent: str | None = None
    guardrail_triggered: bool = False
    highlights: list[PromptHighlight] = Field(default_factory=list)
