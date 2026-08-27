"""Claim/evidence verification factory.

Picks the post-generation claim/evidence verification implementation from the
CLAIM_VERIFICATION_PROVIDER environment variable, mirroring the risk-classifier,
generation-gateway and output-guardrail factories. Unset/empty means the stage
is skipped entirely (generated responses are returned without verification);
"deterministic" wires the fully offline pipeline (extraction + lexical
retrieval over the trusted corpus + support/contradict assessment). Unknown
values fail loudly at startup.
"""

import os


def get_claim_verifier():
    """Return the configured verifier, or None when none is configured."""
    provider = os.getenv("CLAIM_VERIFICATION_PROVIDER", "").strip().lower()
    if not provider:
        return None
    if provider == "deterministic":
        # Imported here so importing the factory never constructs the pipeline
        # (or loads the corpus) until verification is actually needed.
        from services.claim_extraction.extractor import DeterministicClaimExtractor
        from services.claim_verification.service import GeneratedTextVerifier
        from services.evidence_corpus.retrieval import EvidenceRetriever
        from services.evidence_relationship.assessor import (
            DeterministicRelationshipAssessor,
        )

        return GeneratedTextVerifier(
            extractor=DeterministicClaimExtractor(),
            retriever=EvidenceRetriever(),
            assessor=DeterministicRelationshipAssessor(),
        )
    raise ValueError(
        f"Unsupported CLAIM_VERIFICATION_PROVIDER={provider!r}; expected 'deterministic' or unset."
    )
