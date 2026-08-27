"""TC-07 end-to-end: generated unsupported claim handling (risk-gated evidence review).

Full post-generation chain: LLM response -> claim extraction -> evidence
retrieval over the trusted approved-source corpus -> evidence assessment ->
deterministic PolicyEngine -> action determined by risk level. The input prompt
itself is LOW-risk (entirely safe); EVIDENCE-001 is gated by min_risk_level=MEDIUM
so LOW-risk inputs with unsupported claims fall through to the default LOW-risk
rule (ALLOW) instead of escalating to REVIEW. Every stage runs on in-process
fakes/doubles or offline deterministic components — no live provider calls.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api import main as api_main
from apps.api.main import app
from domain.enums import EvidenceRelationship, PolicyAction, RiskLevel, VerificationStatus
from domain.models import (
    AuditEvent,
    Claim,
    ClaimEvidenceAssessment,
    EvidenceAssessment,
)
from services.auth import mint_dev_token
from services.claim_verification import VerifiedResponse
from services.llm import LLMResponse

client = TestClient(app)

ALLOW_PROMPT = "Summarize approved information about Drug X."
UNSUPPORTED_CLAIM = (
    "Clinical trials confirm that Drug X cures the condition with zero side effects."
)


class FakeGateway:
    """In-process LLMGateway double returning canned generated text."""

    def __init__(self, text: str):
        self.text = text
        self.calls: list[str] = []

    async def generate(self, request: Any):
        self.calls.append(request.prompt)
        return LLMResponse(text=self.text)


class FakeVerifier:
    """In-process claim/evidence verifier double with a canned outcome."""

    def __init__(
        self,
        response: VerifiedResponse | None = None,
        error: Exception | None = None,
    ):
        self.response = response
        self.error = error
        self.calls: list[str] = []

    def verify(self, generated_text: str) -> VerifiedResponse:
        self.calls.append(generated_text)
        if self.error is not None:
            raise self.error
        return self.response  # type: ignore[return-value]


class LogRecorder:
    """Captures the AuditEvent objects handed to apps.api.main.log_event."""

    def __init__(self):
        self.events: list[AuditEvent] = []

    def __call__(self, event: AuditEvent) -> None:
        self.events.append(event)

    @property
    def last(self) -> AuditEvent | None:
        return self.events[-1] if self.events else None


def _post(prompt: str, conv: str):
    return client.post(
        "/guardrail/evaluate",
        json={"prompt": prompt, "conversation_id": conv},
        headers={"Authorization": f"Bearer {mint_dev_token('researcher')}"},
    )


def _assessment(
    status: VerificationStatus,
    relationship: EvidenceRelationship | None,
    text: str = UNSUPPORTED_CLAIM,
) -> EvidenceAssessment:
    return EvidenceAssessment(
        claim=Claim(text=text, confidence=0.9),
        status=status,
        relationship=relationship,
        reasoning="checked against approved sources",
        confidence=0.8,
    )


def _response(*assessments: EvidenceAssessment) -> VerifiedResponse:
    return VerifiedResponse(
        assessment=ClaimEvidenceAssessment(assessments=list(assessments)),
        claims_extracted=len(assessments),
        corpus_version="scenario-corpus",
    )


def test_tc07_unsupported_high_risk_claim_is_routed_to_review_end_to_end(monkeypatch):
    """TC-07 core run: LOW-risk prompt in, unsupported claim out -> EVIDENCE-001 REVIEW.

    Even low-risk inputs can produce hallucinations. Evidence verification is
    post-generation output-side checking, so EVIDENCE-001 escalates all
    unsupported claims regardless of input risk level.
    """
    gateway = FakeGateway(UNSUPPORTED_CLAIM)
    verifier = FakeVerifier(
        _response(_assessment(VerificationStatus.UNSUPPORTED, EvidenceRelationship.CONTRADICTS))
    )
    recorder = LogRecorder()
    monkeypatch.setattr("apps.api.main.gateway", gateway)
    monkeypatch.setattr("apps.api.main.claim_verifier", verifier)
    monkeypatch.setattr("apps.api.main.log_event", recorder)

    result = _post(ALLOW_PROMPT, "tc07-unsupported")

    assert result.status_code == 200
    body = result.json()
    # Unsupported claims always escalate via EVIDENCE-001, regardless of input risk.
    assert body["action"] == "REVIEW"
    assert body["decision"]["policy_id"] == "EVIDENCE-001"
    assert body.get("review_required") is True

    # Generation happened exactly once; verification consumed its output.
    assert gateway.calls == [ALLOW_PROMPT]
    assert verifier.calls == [UNSUPPORTED_CLAIM]

    event = recorder.last
    assert event is not None
    # The input side was LOW-risk: EVIDENCE-001 does not gate on LOW-risk.
    assert event.risk_assessment.risk_level == RiskLevel.LOW
    assert event.llm is not None
    assert event.llm.attempted is True
    assert event.llm.succeeded is True

    meta = event.claim_verification
    assert meta is not None
    assert meta.attempted is True
    assert meta.applied is True
    assert meta.succeeded is True
    (stored,) = meta.assessment.assessments
    assert stored.status == VerificationStatus.UNSUPPORTED
    assert stored.relationship == EvidenceRelationship.CONTRADICTS


@pytest.mark.parametrize(
    ("status", "relationship"),
    [
        (VerificationStatus.UNSUPPORTED, EvidenceRelationship.CONFLICTING),
        (VerificationStatus.UNSUPPORTED, None),
        (VerificationStatus.UNVERIFIABLE, EvidenceRelationship.INSUFFICIENT),
    ],
)
def test_tc07_every_non_supported_verdict_routes_to_review(monkeypatch, status, relationship):
    gateway = FakeGateway(UNSUPPORTED_CLAIM)
    verifier = FakeVerifier(_response(_assessment(status, relationship)))
    monkeypatch.setattr("apps.api.main.gateway", gateway)
    monkeypatch.setattr("apps.api.main.claim_verifier", verifier)

    result = _post(ALLOW_PROMPT, f"tc07-{relationship or 'noref'}")

    body = result.json()
    # All unsupported verdicts escalate to EVIDENCE-001 REVIEW regardless of input risk.
    assert body["decision"]["policy_id"] == "EVIDENCE-001"
    assert body["action"] == "REVIEW"


def test_tc07_fully_supported_claim_still_returns_the_response(monkeypatch):
    gateway = FakeGateway("The maximum daily dose is 2000 mg.")
    verifier = FakeVerifier(
        _response(
            _assessment(
                VerificationStatus.SUPPORTED,
                EvidenceRelationship.SUPPORTS,
                text="The maximum daily dose is 2000 mg.",
            )
        )
    )
    recorder = LogRecorder()
    monkeypatch.setattr("apps.api.main.gateway", gateway)
    monkeypatch.setattr("apps.api.main.claim_verifier", verifier)
    monkeypatch.setattr("apps.api.main.log_event", recorder)

    result = _post(ALLOW_PROMPT, "tc07-supported")

    body = result.json()
    assert result.status_code == 200
    assert body["action"] == "ALLOW"
    assert body["response"] == "The maximum daily dose is 2000 mg."
    assert body["decision"]["policy_id"] == "LOW-001"
    assert "review_required" not in body

    meta = recorder.last.claim_verification
    assert meta is not None and meta.applied is True
    assert meta.assessment.all_verified is True


def test_tc07_verification_stage_failure_fails_closed_to_review(monkeypatch):
    gateway = FakeGateway(UNSUPPORTED_CLAIM)
    verifier = FakeVerifier(error=RuntimeError("verifier exploded"))
    recorder = LogRecorder()
    monkeypatch.setattr("apps.api.main.gateway", gateway)
    monkeypatch.setattr("apps.api.main.claim_verifier", verifier)
    monkeypatch.setattr("apps.api.main.log_event", recorder)

    result = _post(ALLOW_PROMPT, "tc07-error")

    body = result.json()
    # Fail closed: an unusable verification stage escalates to REVIEW.
    assert body["decision"]["policy_id"] == "EVIDENCE-001"
    assert body["action"] == "REVIEW"
    assert body.get("review_required") is True
    # internal failure detail must not leak to the caller
    assert "verifier exploded" not in result.text
    assert "RuntimeError" not in result.text

    meta = recorder.last.claim_verification
    assert meta is not None
    assert meta.succeeded is False
    assert meta.failure_kind == "verification_failed"


def test_tc07_without_a_verifier_existing_behavior_is_unchanged(monkeypatch):
    """Regression guard: CLAIM_VERIFICATION_PROVIDER unset keeps the old flow."""
    gateway = FakeGateway("Here is the summary you asked for.")
    recorder = LogRecorder()
    monkeypatch.setattr("apps.api.main.gateway", gateway)
    monkeypatch.setattr("apps.api.main.claim_verifier", None)
    monkeypatch.setattr("apps.api.main.log_event", recorder)

    result = _post(ALLOW_PROMPT, "tc07-off")

    body = result.json()
    assert body["action"] == "ALLOW"
    assert body["response"] == "Here is the summary you asked for."
    event = recorder.last
    assert event is not None
    assert event.claim_verification is None


def test_tc07_real_deterministic_pipeline_catches_contradicted_claim_against_corpus(monkeypatch):
    """The shipped offline pipeline over evidence/approved_sources.yaml itself:
    a polarity-contradicted GLYXTRA dosing claim; on a LOW-risk input, does
    escalate to EVIDENCE-001 REVIEW because the output risk lives in the
    generated content, not the input's risk category.
    """
    from services.claim_extraction.extractor import DeterministicClaimExtractor
    from services.claim_verification.service import GeneratedTextVerifier
    from services.evidence_corpus.retrieval import EvidenceRetriever
    from services.evidence_relationship.assessor import DeterministicRelationshipAssessor

    generated = "GLYXTRA does not require dose adjustment in renal impairment."
    gateway = FakeGateway(generated)
    verifier = GeneratedTextVerifier(
        extractor=DeterministicClaimExtractor(),
        retriever=EvidenceRetriever(),
        assessor=DeterministicRelationshipAssessor(),
    )
    recorder = LogRecorder()
    monkeypatch.setattr("apps.api.main.gateway", gateway)
    monkeypatch.setattr("apps.api.main.claim_verifier", verifier)
    monkeypatch.setattr("apps.api.main.log_event", recorder)

    result = _post(ALLOW_PROMPT, "tc07-real-corpus")

    body = result.json()
    # Contradicted claim escalates to EVIDENCE-001 REVIEW regardless of input risk.
    assert body["decision"]["policy_id"] == "EVIDENCE-001"
    assert body["action"] == "REVIEW"

    # Verification ran and detected the contradiction.
    meta = recorder.last.claim_verification
    assert meta is not None
    assert meta.corpus_version is not None
    (stored,) = meta.assessment.assessments
    assert stored.relationship == EvidenceRelationship.CONTRADICTS
    assert stored.status == VerificationStatus.UNSUPPORTED


def test_tc07_logged_review_decision_is_reproducible_from_the_audit_event_alone(monkeypatch):
    """Rule 3/7 made concrete for the claims flow: re-running the SAME
    deterministic PolicyEngine on only the stored risk assessment + verified
    role + the exact ClaimEvidenceAssessment recorded in the audit event
    reproduces the logged EVIDENCE-001 REVIEW decision byte-for-byte.

    Fresh conversation id guarantees a non-escalating trajectory (empty prior
    window; current turn is LOW and not yet persisted), so replaying without a
    TrajectoryAssessment is equivalent to the original evaluation.
    """
    gateway = FakeGateway(UNSUPPORTED_CLAIM)
    verifier = FakeVerifier(
        _response(_assessment(VerificationStatus.UNSUPPORTED, EvidenceRelationship.CONTRADICTS))
    )
    recorder = LogRecorder()
    monkeypatch.setattr("apps.api.main.gateway", gateway)
    monkeypatch.setattr("apps.api.main.claim_verifier", verifier)
    monkeypatch.setattr("apps.api.main.log_event", recorder)

    result = _post(ALLOW_PROMPT, "tc07-reproducible")

    body = result.json()
    assert body["decision"]["policy_id"] == "EVIDENCE-001"
    assert body["action"] == "REVIEW"

    event = recorder.last
    assert event is not None
    assert event.claim_verification is not None

    replayed = api_main.policy_engine.evaluate(
        event.risk_assessment,
        event.user_role,
        claims=event.claim_verification.assessment,
    )

    original = event.policy_decision
    assert replayed.action == PolicyAction.REVIEW == original.action
    assert replayed.policy_id == "EVIDENCE-001" == original.policy_id
    # Full equality apart from the wall-clock timestamp: same policy version,
    # reasons and required controls from exactly the stored evidence.
    assert replayed.model_dump(exclude={"timestamp"}) == original.model_dump(exclude={"timestamp"})
