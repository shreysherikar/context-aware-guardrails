"""Claim/evidence verification orchestrator contracts.

VerifiedResponse bundles the domain ClaimEvidenceAssessment (the structured
evidence the deterministic PolicyEngine consumes) with the provenance signals
auditors need to reproduce the decision: which corpus version grounded it and
which retrieval/relationship implementations produced the verdicts.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from domain.enums import EvidenceRelationship, VerificationStatus
from domain.models import (
    Claim,
    ClaimEvidenceAssessment,
    ClaimVerificationMeta,
    EvidenceAssessment,
)
from services.evidence_corpus.models import RETRIEVAL_VERSION
from services.evidence_relationship.models import RELATIONSHIP_VERSION

VERIFIER_VERSION = "1.0.0"

# Mapping from the corpus assessor's coarse relationship vocabulary to the
# per-claim verification status recorded on EvidenceAssessment. Deliberately
# conservative in every direction:
#   SUPPORTS     -> SUPPORTED     (every applicable passage agrees)
#   CONTRADICTS  -> UNSUPPORTED   (approved sources say otherwise)
#   CONFLICTING  -> UNSUPPORTED   (sources disagree; cannot auto-approve)
#   INSUFFICIENT -> UNVERIFIABLE  (nothing applicable available to judge)
# Unknown values can never reach this function without first failing pydantic
# validation of the enum itself; anything not explicitly mapped below resolves
# to UNVERIFIABLE — never to SUPPORTED (fail closed).
_RELATIONSHIP_TO_STATUS: dict[EvidenceRelationship, VerificationStatus] = {
    EvidenceRelationship.SUPPORTS: VerificationStatus.SUPPORTED,
    EvidenceRelationship.CONTRADICTS: VerificationStatus.UNSUPPORTED,
    EvidenceRelationship.CONFLICTING: VerificationStatus.UNSUPPORTED,
    EvidenceRelationship.INSUFFICIENT: VerificationStatus.UNVERIFIABLE,
}


def relationship_to_status(relationship: EvidenceRelationship) -> VerificationStatus:
    """Map an assessed relationship to its per-claim verification status."""
    status = _RELATIONSHIP_TO_STATUS.get(relationship)
    if status is None:
        # A future enum member must resolve conservatively, never to SUPPORTED.
        return VerificationStatus.UNVERIFIABLE
    return status


class VerifiedResponse(BaseModel):
    """Structured output of verifying ONE generated response's claims.

    Modeled on RetrievalResult / EvidenceRelationshipResult: minimal failure
    signals (succeeded / error_kind) plus the payload. The payload IS the
    domain aggregate consumed by the deterministic PolicyEngine — this model
    adds provenance only, never authority.
    """

    # Fields no member of this package may ever grow (structural guard).
    FORBIDDEN_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"action", "decision", "policy_id", "policy_version"}
    )

    assessment: ClaimEvidenceAssessment
    claims_extracted: int = Field(ge=0, default=0)
    corpus_version: str | None = None
    retrieval_version: str = RETRIEVAL_VERSION
    relationship_version: str = RELATIONSHIP_VERSION
    verifier_version: str = VERIFIER_VERSION
    succeeded: bool = True
    error_kind: str | None = None


def unverified_failure_response(reason: str, *, error_kind: str) -> VerifiedResponse:
    """Build the conservative response for ANY internal verification failure.

    A synthetic single UNVERIFIABLE claim keeps the aggregate ``all_verified``
    False, so supplying it to the deterministic PolicyEngine routes the response
    to EVIDENCE-001 REVIEW instead of silently falling back to ALLOW. Failure is
    never represented by an empty (vacuously verified) assessment.
    """
    return VerifiedResponse(
        assessment=ClaimEvidenceAssessment(
            assessments=[
                EvidenceAssessment(
                    claim=Claim(text="[claim verification unavailable]", confidence=0.0),
                    status=VerificationStatus.UNVERIFIABLE,
                    reasoning=f"verification degraded conservatively: {reason}",
                    confidence=0.0,
                )
            ]
        ),
        claims_extracted=0,
        succeeded=False,
        error_kind=error_kind,
    )


def build_audit_meta(
    verification: VerifiedResponse,
    *,
    attempted: bool = True,
) -> ClaimVerificationMeta:
    """Reduce one VerifiedResponse to its audit-facing claims-verification meta."""
    return ClaimVerificationMeta(
        attempted=attempted,
        succeeded=verification.succeeded,
        applied=verification.claims_extracted > 0,
        assessment=verification.assessment,
        corpus_version=verification.corpus_version,
        retrieval_version=verification.retrieval_version,
        relationship_version=verification.relationship_version,
        verifier_version=verification.verifier_version,
        failure_kind=verification.error_kind,
    )
