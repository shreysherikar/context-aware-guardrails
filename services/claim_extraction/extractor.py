"""Claim extraction from generated responses (services/claim_extraction).

First stage of the post-generation claim/evidence verification flow: splits one
LLM-generated response into atomic factual claims for later per-claim evidence
retrieval and assessment. The offline implementation is fully deterministic —
the same text always yields the same claims in the same order — so business
logic stays unit-testable without any live model (repo testing rules).

STRUCTURAL CONSTRAINT: this component is incapable of producing a PolicyAction
or PolicyDecision. It returns domain Claim records (text + confidence only),
exactly like the rest of the evidence plane. Extraction carries no stance on a
claim's truthfulness; what happens to an unverified claim belongs solely to the
deterministic PolicyEngine.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from domain.models import Claim

logger = logging.getLogger(__name__)

CLAIM_EXTRACTION_VERSION = "1.0.0"

# Uniform confidence assigned by the offline extractor: deterministic sentence
# segmentation gives no basis for per-sentence confidence differentiation. A
# future model-backed extractor may emit calibrated values instead.
DEFAULT_CLAIM_CONFIDENCE = 0.5

# Upper bound on claims extracted from ONE response. Without a cap, a very long
# generation would drive unbounded retrieval work (one corpus load + score per
# claim). First-N-in-order keeps the outcome deterministic under truncation.
DEFAULT_MAX_CLAIMS = 10

# Sentences shorter than this cannot meaningfully assert anything checkable.
MIN_CLAIM_LENGTH = 4

# Sentence boundaries: terminal punctuation followed by whitespace, or hard
# line breaks (markdown bullets / list items are claim boundaries too).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
# Common markdown-ish bullet prefixes stripped before a sentence becomes a
# Claim (they are formatting, not part of the assertion).
_BULLET_PREFIX_RE = re.compile(r"^(?:[-*•]\s+|\d+[.)]\s+)")
_HAS_CONTENT_RE = re.compile(r"[a-z0-9]")


class ClaimExtractionError(RuntimeError):
    """Raised when claim extraction fails internally."""


class ClaimExtractor(ABC):
    """Contract for extracting claims from generated text.

    Any implementation — the offline default or a future model-backed one
    behind this same interface — returns structured Claim records only.
    Implementations raise ClaimExtractionError on internal failure rather than
    silently returning an empty list: an empty result would make verification
    vacuously pass (ALLOW) when it must degrade conservatively (fail closed).
    """

    @abstractmethod
    def extract(self, generated_text: str) -> list[Claim]:
        """Return extracted claims in stable order. Raises ClaimExtractionError."""


class DeterministicClaimExtractor(ClaimExtractor):
    """Offline sentence-segmentation extractor. No network, no LLM."""

    def __init__(
        self,
        *,
        max_claims: int = DEFAULT_MAX_CLAIMS,
        confidence: float = DEFAULT_CLAIM_CONFIDENCE,
    ):
        if max_claims < 1:
            raise ValueError("max_claims must be at least 1")
        self._max_claims = max_claims
        self._confidence = confidence

    def extract(self, generated_text: str) -> list[Claim]:
        """Split ``generated_text`` into unique, ordered sentences. Never raises.

        Any unexpected error resolves to an explicit ClaimExtractionError
        (logged) instead of propagating mid-pipeline: downstream stages convert
        it into a conservative unverifiable verdict.
        """
        try:
            return self._extract(generated_text)
        except Exception as exc:  # noqa: BLE001 - deliberate fail-conservative conversion
            logger.warning("Claim extraction failed", exc_info=True)
            raise ClaimExtractionError(
                f"claim extraction failed internally: {type(exc).__name__}"
            ) from exc

    def _extract(self, generated_text: str) -> list[Claim]:
        if not isinstance(generated_text, str):
            raise TypeError(f"expected str, got {type(generated_text).__name__}")

        claims: list[Claim] = []
        seen: set[str] = set()
        for raw_sentence in _SENTENCE_SPLIT_RE.split(generated_text.strip()):
            sentence = _BULLET_PREFIX_RE.sub("", raw_sentence.strip())
            if len(sentence) < MIN_CLAIM_LENGTH:
                continue
            if not _HAS_CONTENT_RE.search(sentence.casefold()):
                continue
            key = sentence.casefold()
            # Exact-duplicate sentences carry no additional verifiable content;
            # deduping keeps one assessment per distinct assertion.
            if key in seen:
                continue
            seen.add(key)
            claims.append(Claim(text=sentence, confidence=self._confidence))
            if len(claims) >= self._max_claims:
                break
        return claims


__all__ = [
    "CLAIM_EXTRACTION_VERSION",
    "DEFAULT_CLAIM_CONFIDENCE",
    "DEFAULT_MAX_CLAIMS",
    "MIN_CLAIM_LENGTH",
    "ClaimExtractionError",
    "ClaimExtractor",
    "DeterministicClaimExtractor",
]
