"""
Domain contracts.

These models have NO dependency on FastAPI, LangGraph, any LLM SDK, or any
database. They are the stable interface that every other module is written
against, so that swapping FastAPI for something else, or a mock classifier
for a real LLM, never requires touching business logic.

The single most important rule encoded here: RiskAssessment has no `action`
or `decision` field. The classifier that produces it is never allowed to
authorize anything — only the PolicyEngine (services/policy_engine) can
produce a PolicyDecision.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from domain.enums import DataSensitivity, PolicyAction, RiskCategory, RiskLevel


class GuardrailRequest(BaseModel):
    """Client-supplied request payload.

    Identity is NOT part of the request body: the caller's role comes
    exclusively from a verified bearer token (see services/auth), so there is
    exactly one identity source and role-based policy rules cannot be spoofed
    by request fields.
    """

    prompt: str
    conversation_id: str
    requested_action: str | None = None


class RiskAssessment(BaseModel):
    """Structured, probabilistic output of the risk/reasoning plane."""

    risk_level: RiskLevel
    categories: list[RiskCategory] = Field(default_factory=list)
    disguise_detected: bool = False
    injection_detected: bool = False
    data_sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    reasoning: str = ""


class PolicyDecision(BaseModel):
    """Deterministic, auditable output of the policy plane. This is authority."""

    action: PolicyAction
    policy_id: str
    policy_version: str
    reasons: list[str] = Field(default_factory=list)
    required_controls: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LLMResult(BaseModel):
    """Outcome of the post-ALLOW LLM generation step, for audit purposes.

    Only the minimal signal the pipeline needs is stored: whether generation
    was attempted, whether it succeeded, and a short failure kind on error.
    Raw provider/exception text is never recorded here.
    """

    attempted: bool
    succeeded: bool
    error_kind: str | None = None


class OutputAssessment(BaseModel):
    """Structured output of the output guardrail (post-generation check).

    Structured metadata only: it carries no authority to decide the final
    outcome. The API layer decides whether to route the response to
    flagged-for-review based on `flagged`. For this milestone, "unverified"
    means "not supported by what is actually in the prompt" — there is no
    separate approved-source/RAG store yet.
    """

    flagged: bool
    unverified_claims: list[str] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class OutputGuardrailResult(BaseModel):
    """Outcome of the output-guardrail step, for audit purposes.

    Mirrors LLMResult: minimal signals (attempted / flagged / error kind),
    no generated text or provider detail is stored.
    """

    attempted: bool
    flagged: bool
    error_kind: str | None = None


class OCREntity(BaseModel):
    """A span extracted by OCR (evidence only — never a policy decision)."""

    label: str
    text: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    bbox: list[float] | None = None


class OCRResult(BaseModel):
    """Structured OCR output. Carries no ALLOW/BLOCK authority."""

    text: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    entities: list[OCREntity] = Field(default_factory=list)


class OpticalFinding(BaseModel):
    """One optical-analysis finding. Evidence only — not a policy action."""

    type: str
    category: RiskCategory
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    text: str | None = None
    bbox: list[float] | None = None


class OpticalAssessment(BaseModel):
    """Optical-plane assessment. Must never carry a final policy action.

    Downstream code normalizes this into a RiskAssessment; only the
    PolicyEngine may produce a PolicyDecision.
    """

    ocr_text: str
    document_type: str | None = None
    findings: list[OpticalFinding] = Field(default_factory=list)
    face_detected: bool = False
    injection_detected: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class OpticalAuditMeta(BaseModel):
    """Audit metadata for optical/image requests. No raw images or PHI OCR."""

    input_type: str = "image"
    ocr_used: bool = True
    optical_analysis_used: bool = True
    document_type: str | None = None
    finding_count: int = 0
    sanitization_applied: bool = False
    image_sha256: str | None = None


class SanitizationAuditMeta(BaseModel):
    """Audit signals for REWRITE sanitization — no raw PHI values."""

    attempted: bool = False
    succeeded: bool = False
    applied: bool = False
    input_type: str = "text"
    finding_count: int = 0
    sanitizer_version: str = "1.0.0"
    sanitized_context_used: bool = False
    failure_kind: str | None = None


class AuditEvent(BaseModel):
    conversation_id: str
    prompt: str
    # The role taken from the verified bearer token (never a raw request field).
    user_role: str
    risk_assessment: RiskAssessment
    policy_decision: PolicyDecision
    llm: LLMResult | None = None
    output_guardrail: OutputGuardrailResult | None = None
    optical: OpticalAuditMeta | None = None
    sanitization: SanitizationAuditMeta | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
