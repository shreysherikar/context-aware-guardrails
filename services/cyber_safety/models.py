"""Models for dark-web access prevention assessments."""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.enums import RiskLevel


class DarkWebAssessment(BaseModel):
    """Semantic assessment of dark-web-related content."""

    risk_level: RiskLevel = RiskLevel.LOW
    decision: str = "ALLOW"  # ALLOW | REWRITE | BLOCK | REVIEW
    policy_id: str = "DARKWEB_ACCESS_PREVENTION"
    categories: list[str] = Field(default_factory=list)
    actionable: bool = False
    educational: bool = False
    data_exfiltration: bool = False
    injection_attempt: bool = False
    computer_use_attempt: bool = False
    reasons: list[str] = Field(default_factory=list)
    security_event_category: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)


class ProcessedOutput(BaseModel):
    """Result of output-side dark-web processing with mandatory re-evaluation."""

    text: str
    original_blocked: bool = False
    rewrite_applied: bool = False
    flagged: bool = False
    assessment: DarkWebAssessment | None = None
