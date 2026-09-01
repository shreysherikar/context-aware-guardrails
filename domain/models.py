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

from domain.enums import (
    DataSensitivity,
    EvidenceRelationship,
    PolicyAction,
    ResolutionType,
    RiskCategory,
    RiskLevel,
    VerificationStatus,
)


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


class TrajectoryAssessment(BaseModel):
    """Deterministic evidence about a conversation's risk trajectory.

    Produced by services/trajectory_engine over stored audit history. This is
    evidence only: it carries no PolicyAction, no policy_id, and no method that
    could be mistaken for a decision. The PolicyEngine consumes `escalate` as
    one condition among others and remains the sole producer of PolicyDecision.
    """

    escalate: bool = False
    reason: str = ""
    medium_or_above_count: int = 0
    repeated_category: RiskCategory | None = None
    non_decreasing_trend: bool = False


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
    safe_text: str | None = None
    blocked: bool = False
    rewrite_applied: bool = False


class OutputGuardrailResult(BaseModel):
    """Outcome of the output-guardrail step, for audit purposes.

    Mirrors LLMResult: minimal signals (attempted / flagged / error kind),
    no generated text or provider detail is stored.
    """

    attempted: bool
    flagged: bool
    error_kind: str | None = None


# Claim/evidence verification — planned feature, contracts only for now.
# Same family as TrajectoryAssessment/OpticalAssessment: structured metadata
# produced outside the policy plane, consumed by it as one condition among
# others. Nothing here carries authority.


class Claim(BaseModel):
    """One atomic factual claim extracted from generated text.

    Extraction output is evidence only: a claim record takes no stance on its
    own truthfulness and carries nothing that could authorize or reject it.
    """

    text: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class Evidence(BaseModel):
    """One piece of approved-source material offered as grounding for a claim.

    `source_id` names the specific approved source, so any later audit event
    is reproducible from exactly which sources did (or did not) back a claim.
    """

    source_id: str
    text: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class EvidenceAssessment(BaseModel):
    """Verification verdict for ONE claim against approved-source evidence.

    Structured metadata only. It intentionally has no `action`/`decision`
    field: what happens to an unsupported claim is determined solely by the
    deterministic PolicyEngine (and the API layer), never by this record.
    """

    claim: Claim
    status: VerificationStatus
    # Optional finer-grained verdict from the deterministic corpus assessor
    # (services/evidence_relationship): SUPPORTS / CONTRADICTS / INSUFFICIENT /
    # CONFLICTING. Recorded only when verification ran against retrieved
    # approved-source passages; None means the claim was judged without that
    # stage. Evidence only — like `status`, it never authorizes anything, and
    # when it disagrees with `status`, every derived view resolves to the
    # weaker reading (see ClaimEvidenceAssessment.all_verified).
    relationship: EvidenceRelationship | None = None
    supporting_evidence: list[Evidence] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class ClaimEvidenceAssessment(BaseModel):
    """Aggregate claim/evidence verification of one generated response.

    Evidence in, no PolicyDecision out. `unverified_claims` and
    `all_supported` are derived views over `assessments` (computed on every
    access), so the summary an auditor reads can never disagree with the
    per-claim detail — and any status other than SUPPORTED counts as
    unverified, keeping the aggregate conservative against future enum values.
    """

    assessments: list[EvidenceAssessment] = Field(default_factory=list)

    @property
    def unverified_claims(self) -> list[str]:
        """Texts of every claim not SUPPORTED, in assessment order."""
        return [
            assessment.claim.text
            for assessment in self.assessments
            if assessment.status != VerificationStatus.SUPPORTED
        ]

    @property
    def all_supported(self) -> bool:
        """True when nothing is unverified; vacuously true with no claims.

        Mirrors OutputAssessment semantics: absence of flagged content is not
        itself a finding.
        """
        return all(
            assessment.status == VerificationStatus.SUPPORTED for assessment in self.assessments
        )

    @property
    def all_verified(self) -> bool:
        """True only when every claim clears BOTH verdict levels, conservatively.

        A claim counts as verified solely when its status is SUPPORTED and,
        where a corpus relationship was recorded, that relationship is
        SUPPORTS. Every other combination counts as not verified, including
        statuses/relationships added to either enum later (unknown values are
        never trusted) and disagreeing metadata such as a SUPPORTED status
        alongside CONTRADICTS/CONFLICTING/INSUFFICIENT. The aggregate can
        therefore never certify a claim more strongly than its weakest
        metadata (fail closed). Vacuously true with no claims, mirroring
        ``all_supported``: absence of assessed content is not itself a
        finding. This is the view the deterministic PolicyEngine reads; like
        every member of this model family it carries no authority of its own.
        """
        return all(
            assessment.status == VerificationStatus.SUPPORTED
            and (
                assessment.relationship is None
                or assessment.relationship == EvidenceRelationship.SUPPORTS
            )
            for assessment in self.assessments
        )


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
    trust: str | None = None
    threat_category: str | None = None


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
    trust_classification: str = "untrusted"
    multimodal_categories: list[str] = Field(default_factory=list)
    rewrite_mode: str | None = None
    qr_detected: bool = False
    qr_payload: str | None = None
    authority_spoofing: bool = False
    data_exfiltration: bool = False


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


class ClaimVerificationMeta(BaseModel):
    """Audit signals for post-generation claim/evidence verification.

    ``assessment`` stores the EXACT structured evidence the deterministic
    PolicyEngine consumed for its EVIDENCE-001 evaluation (per-claim status,
    relationship, and supporting source IDs), so a claims-driven REVIEW can be
    reproduced from the audit record plus risk assessment, verified role and
    policy version alone. Provenance versions name the corpus revision and the
    retrieval/relationship implementations that produced the verdicts. Like the
    other audit metadata here, generated response text itself is never stored.
    """

    # Stage ran for this generated response.
    attempted: bool = False
    # Stage completed without internal failure; failures carry failure_kind.
    succeeded: bool = True
    # Claims were actually extracted and assessed (a clean run with zero
    # verifiable sentences is applied=False).
    applied: bool = False
    # Exact evidence input to the deterministic PolicyEngine (may be empty —
    # absence of assessed content is not itself a finding, mirroring
    # OutputAssessment: an empty aggregate verifies vacuously in policy terms).
    assessment: ClaimEvidenceAssessment = Field(default_factory=ClaimEvidenceAssessment)
    corpus_version: str | None = None
    retrieval_version: str = ""
    relationship_version: str = ""
    verifier_version: str = ""
    failure_kind: str | None = None


class ResolutionPath(BaseModel):
    """One available resolution option for a guarded request."""

    type: ResolutionType
    title: str
    message: str
    primary: bool = False


class LLMStatusStep(BaseModel):
    """One step in the LLM forwarding status strip."""

    label: str
    status: str  # forwarded | not_forwarded | pending | completed | not_contacted


class ExplainableDecision(BaseModel):
    """User-facing safety decision — no internal guardrail implementation details."""

    request_id: str
    decision: PolicyAction
    forwarded_to_llm: bool
    category: str
    reason: str
    detected_elements: list[str] = Field(default_factory=list)
    resolution_type: ResolutionType
    resolution_message: str
    safe_suggestions: list[str] = Field(default_factory=list)
    available_resolutions: list[ResolutionPath] = Field(default_factory=list)
    llm_status: list[LLMStatusStep] = Field(default_factory=list)
    sanitized_prompt: str | None = None
    original_prompt_protected: bool = False


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
    claim_verification: ClaimVerificationMeta | None = None
    request_id: str = ""
    resolution_type: str | None = None
    forwarded_to_llm: bool = False
    sanitization_occurred: bool = False
    human_review_requested: bool = False
    human_review_outcome: str | None = None
    report_status: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
