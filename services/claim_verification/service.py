"""Post-generation claim/evidence verification orchestration (evidence plane).

Composes the offline stages over one generated LLM response: claim extraction
-> trusted-corpus retrieval per claim -> evidence-relationship assessment ->
aggregated domain ClaimEvidenceAssessment with full provenance.

STRUCTURAL CONSTRAINT: nothing here produces a PolicyAction or a
PolicyDecision. ``verify()`` returns VerifiedResponse carrying evidence plus
provenance; the caller feeds ``assessment`` to the deterministic PolicyEngine,
which alone decides what happens to unsupported claims (EVIDENCE-001 REVIEW).

FAIL-CLOSED CONTRACT: verify() never raises. Any internal failure in any stage
resolves to succeeded=False with a synthetic UNVERIFIABLE claim whose aggregate
all_verified is False — a verification outage therefore degrades to human
review via policy, never to a silent allow-through.
"""

from __future__ import annotations

import logging

from domain.enums import EvidenceRelationship
from domain.models import (
    Claim,
    ClaimEvidenceAssessment,
    Evidence,
    EvidenceAssessment,
)
from services.claim_extraction.extractor import ClaimExtractionError, ClaimExtractor
from services.claim_verification.models import (
    VerifiedResponse,
    relationship_to_status,
    unverified_failure_response,
)
from services.evidence_corpus.retrieval import EvidenceRetriever, RetrievalResult
from services.evidence_relationship.assessor import EvidenceRelationshipAssessor

logger = logging.getLogger(__name__)


class GeneratedTextVerifier:
    """Extract, retrieve per claim, assess per claim, aggregate. Never decides."""

    def __init__(
        self,
        extractor: ClaimExtractor,
        retriever: EvidenceRetriever,
        assessor: EvidenceRelationshipAssessor,
    ):
        self._extractor = extractor
        self._retriever = retriever
        self._assessor = assessor

    def verify(self, generated_text: str) -> VerifiedResponse:
        """Run the pipeline over ``generated_text``. Never raises.

        On any internal failure returns succeeded=False with a conservative
        aggregate (one synthetic UNVERIFIABLE claim), which downstream policy
        evaluation routes to EVIDENCE-001 REVIEW rather than ALLOW.
        """
        try:
            return self._verify(generated_text)
        except Exception as exc:  # noqa: BLE001 - fail closed with a reason
            logger.warning(
                "Claim/evidence verification failed; degrading to unverified",
                exc_info=True,
            )
            return unverified_failure_response(
                type(exc).__name__,
                error_kind="verification_failed",
            )

    def _verify(self, generated_text: str) -> VerifiedResponse:
        try:
            claims = self._extractor.extract(generated_text)
        except ClaimExtractionError as exc:
            # Extraction failure must degrade conservatively, not look like a
            # claim-free response (an empty aggregate would verify vacuously).
            raise RuntimeError(f"extraction unavailable: {exc}") from exc

        assessments: list[EvidenceAssessment] = []
        corpus_version: str | None = None
        for claim in claims:
            retrieval = self._retrieve(claim)
            if retrieval.corpus_version is not None:
                corpus_version = retrieval.corpus_version
            assessments.append(self._assess_claim(claim, retrieval))

        return VerifiedResponse(
            assessment=ClaimEvidenceAssessment(assessments=assessments),
            claims_extracted=len(claims),
            corpus_version=corpus_version,
        )

    def _assess_claim(self, claim: Claim, retrieval: RetrievalResult) -> EvidenceAssessment:
        """Judge one claim against its retrieved approved-source passages."""
        evidence: list[Evidence] = (
            [
                Evidence(
                    source_id=match.source_id,
                    text=match.text,
                    confidence=match.confidence,
                )
                for match in retrieval.matches
            ]
            if retrieval.succeeded
            else []
        )
        relationship_result = self._assessor.assess(claim, evidence)

        # Supporting passages are cited only when EVERY applicable passage agrees
        # (aggregate SUPPORTS): under CONFLICTING/CONTRADICTS the agree-set must
        # never read like approval provenance (fail closed).
        supporting_evidence = (
            [
                Evidence(
                    source_id=item.source_id,
                    text=item.text,
                    confidence=item.confidence,
                )
                for item in relationship_result.items
                if item.relationship == EvidenceRelationship.SUPPORTS
            ]
            if relationship_result.relationship == EvidenceRelationship.SUPPORTS
            else []
        )

        if retrieval.succeeded:
            reasoning = (
                f"{len(retrieval.matches)} passage(s) retrieved from the approved "
                f"corpus; {relationship_result.reasoning}"
            )
            confidence = max(
                (item.match_strength for item in relationship_result.items),
                default=0.0,
            )
        else:
            # Unavailable evidence cannot look like support: a failed retrieval
            # behaves exactly like an empty corpus for this claim.
            reasoning = (
                f"evidence retrieval unavailable ({retrieval.error_kind}); "
                f"{relationship_result.reasoning}"
            )
            confidence = 0.0

        return EvidenceAssessment(
            claim=claim,
            status=relationship_to_status(relationship_result.relationship),
            relationship=relationship_result.relationship,
            supporting_evidence=supporting_evidence,
            reasoning=reasoning,
            confidence=confidence,
        )

    def _retrieve(self, claim: Claim) -> RetrievalResult:
        try:
            return self._retriever.retrieve_for_claim(claim)
        except Exception:  # noqa: BLE001 - defensive depth: retrievers never raise upstream
            logger.warning("Unexpected retriever failure", exc_info=True)
            return RetrievalResult(query=claim.text, succeeded=False, error_kind="unknown")


__all__ = ["GeneratedTextVerifier"]
