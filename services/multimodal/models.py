"""Models for multimodal untrusted-content analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.enums import RiskLevel


class ExtractedElement(BaseModel):
    """One piece of content extracted from an image with trust classification."""

    element_type: str
    content: str
    trust: str  # DATA | UNTRUSTED_INSTRUCTION | UNTRUSTED_AUTHORITY | UNTRUSTED_URL | UNTRUSTED_QR
    threat_category: str | None = None
    start: int | None = None
    end: int | None = None
    severity: str = "medium"


class MultimodalAssessment(BaseModel):
    """Full assessment of multimodal (image/OCR/screen) content."""

    risk_level: RiskLevel = RiskLevel.LOW
    decision: str = "ALLOW"  # ALLOW | REWRITE | REVIEW | BLOCK
    rewrite_mode: str = (
        "PASS"  # PASS | ANNOTATE | REDACT | MASK | REMOVE | SAFE_REWRITE | REVIEW | BLOCK
    )
    categories: list[str] = Field(default_factory=list)
    elements: list[ExtractedElement] = Field(default_factory=list)
    injection_detected: bool = False
    authority_spoofing: bool = False
    data_exfiltration: bool = False
    credential_exposure: bool = False
    malicious_url: bool = False
    phishing: bool = False
    malware_instruction: bool = False
    computer_use_manipulation: bool = False
    policy_bypass: bool = False
    qr_detected: bool = False
    qr_payload: str | None = None
    reasons: list[str] = Field(default_factory=list)
    security_event_category: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)


class ProcessedMultimodal(BaseModel):
    """Result after multimodal rewrite with mandatory re-evaluation."""

    text: str
    rewrite_applied: bool = False
    blocked: bool = False
    assessment: MultimodalAssessment | None = None
