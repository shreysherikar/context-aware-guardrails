"""Claim extraction from generated responses (evidence plane only).

Deterministic sentence segmentation of LLM output into Claim records for later
evidence retrieval and assessment. Nothing here produces a PolicyAction or a
PolicyDecision, and failures raise an explicit error rather than producing an
empty-looking success (fail closed — see extractor.ClaimExtractionError).
"""

from services.claim_extraction.extractor import (
    CLAIM_EXTRACTION_VERSION,
    DEFAULT_CLAIM_CONFIDENCE,
    DEFAULT_MAX_CLAIMS,
    MIN_CLAIM_LENGTH,
    ClaimExtractionError,
    ClaimExtractor,
    DeterministicClaimExtractor,
)

__all__ = [
    "CLAIM_EXTRACTION_VERSION",
    "DEFAULT_CLAIM_CONFIDENCE",
    "DEFAULT_MAX_CLAIMS",
    "MIN_CLAIM_LENGTH",
    "ClaimExtractionError",
    "ClaimExtractor",
    "DeterministicClaimExtractor",
]
