"""Sanitization contracts — evidence only, never a PolicyAction."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from domain.enums import RiskCategory
from domain.models import OpticalFinding

SANITIZER_VERSION = "1.0.0"

SourceType = Literal["text", "image"]


class SanitizationFinding(BaseModel):
    """One redaction applied (or attempted). Avoid storing raw PHI in audits.

    ``original_value`` is kept in-memory for the sanitization pass only and
    must not be written to durable audit storage.
    """

    entity_type: str
    category: RiskCategory
    replacement: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    source: SourceType = "text"
    location: str | None = None
    # In-memory only — callers must not persist this to audit.
    original_value: str | None = None


class SanitizationRequest(BaseModel):
    """Input to the sanitization engine."""

    text: str
    source_type: SourceType = "text"
    optical_findings: list[OpticalFinding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SanitizationResult(BaseModel):
    """Safe context produced by sanitization. No policy authority."""

    sanitized_text: str
    sanitized: bool = True
    findings: list[SanitizationFinding] = Field(default_factory=list)
    changed: bool = False
    success: bool = True
    failure_reason: str | None = None
    source_type: SourceType = "text"
    sanitizer_version: str = SANITIZER_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)
