"""Models for guardrail human-review workflow."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from domain.enums import PolicyAction, ReviewRequestStatus


class EvaluationSnapshot(BaseModel):
    """Stored context for a completed guardrail evaluation."""

    request_id: str
    conversation_id: str
    user_role: str
    effective_decision: PolicyAction
    policy_action: PolicyAction
    prompt: str
    input_type: str = "text"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GuardrailReviewRequest(BaseModel):
    """A user-initiated human review request."""

    review_request_id: str
    evaluation_request_id: str
    conversation_id: str
    user_role: str
    effective_decision: PolicyAction
    status: ReviewRequestStatus = ReviewRequestStatus.PENDING
    note: str | None = None
    approver: str | None = None
    outcome: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DecisionReport(BaseModel):
    """User report that a guardrail decision was incorrect."""

    report_id: str
    evaluation_request_id: str
    conversation_id: str
    user_role: str
    comment: str | None = None
    status: str = "SUBMITTED"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
