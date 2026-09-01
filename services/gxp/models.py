"""Models for GxP compliance review results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GxpHighlight(BaseModel):
    """Span in source text that violates GxP expectations."""

    start: int
    end: int
    text: str
    gxp_frameworks: list[str] = Field(default_factory=list)
    category: str
    reason: str
    severity: str = "medium"
    suggested_replacement: str = ""
    principle: str = ""


class GxpFinding(BaseModel):
    """One GxP issue with remediation guidance."""

    phrase: str
    gxp_frameworks: list[str] = Field(default_factory=list)
    category: str
    reason: str
    severity: str = "medium"
    suggested_replacement: str = ""
    principle: str = ""
    references: list[str] = Field(default_factory=list)


class GxpReviewResult(BaseModel):
    """Full GxP review of a document or procedure text."""

    original_text: str
    rewritten_text: str
    compliant: bool
    finding_count: int
    highlights: list[GxpHighlight] = Field(default_factory=list)
    findings: list[GxpFinding] = Field(default_factory=list)
    gxp_frameworks_applied: list[str] = Field(default_factory=list)
    summary: str = ""
