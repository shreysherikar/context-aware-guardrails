"""Post-generation claim/evidence verification (evidence plane).

Orchestrates claim extraction -> trusted-corpus retrieval -> support/contradict
assessment over one generated LLM response, producing the structured
ClaimEvidenceAssessment that the deterministic PolicyEngine consumes. Nothing
here produces a PolicyAction or a PolicyDecision, and any internal failure
degrades conservatively to an unverifiable aggregate (fail closed), never to a
vacuous allow-through.
"""

from services.claim_verification.models import (
    VERIFIER_VERSION,
    VerifiedResponse,
    build_audit_meta,
    relationship_to_status,
    unverified_failure_response,
)
from services.claim_verification.service import GeneratedTextVerifier

__all__ = [
    "VERIFIER_VERSION",
    "GeneratedTextVerifier",
    "VerifiedResponse",
    "build_audit_meta",
    "relationship_to_status",
    "unverified_failure_response",
]
