"""Deterministic evidence-relationship assessment (services/evidence_relationship).

Judges the relationship between one extracted claim and the approved-source
passages already retrieved for it. Fully deterministic lexical comparison —
no LLM call happens here, ever, and input ordering is preserved verbatim — so
the same claim against the same passages always yields the same result.

Per-passage algorithm:
  1. Lexical coverage: fraction of distinct claim terms present in the
     passage. Passages below ``applicability_threshold`` do not bear on the
     verdict at all; they are recorded as INSUFFICIENT signals.
  2. Polarity: a text counts as negative when it contains a negation cue
     ("not", "no", "never", ...) and positive otherwise. Disagreement between
     claim polarity and passage polarity resolves to CONTRADICTS; agreement
     resolves to SUPPORTS. Two negated texts agree (double negative reads as
     affirmation).

Aggregate rule: SUPPORTS / CONTRADICTS when every applicable passage agrees;
CONFLICTING when applicable passages disagree among themselves; INSUFFICIENT
otherwise — including when nothing applicable was found. Deliberately coarse:
multi-clause sentences, stemming, and predicate-level negation scope are out
of scope for this milestone, and any ambiguity lands on INSUFFICIENT, which
consumers must treat as unsupported-by-evidence (conservative direction).

STRUCTURAL CONSTRAINT: this component is incapable of producing a PolicyAction
or PolicyDecision. It returns EvidenceRelationshipResult (relationship +
provenance only, exactly like RetrievalResult). Any internal failure degrades
to an explicit INSUFFICIENT result with error_kind recorded — never to
SUPPORTS — and the exception is logged loudly so evidence outages are
observable.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence

from domain.enums import EvidenceRelationship
from domain.models import Claim, Evidence
from services.evidence_relationship.models import (
    RELATIONSHIP_VERSION,
    AssessedEvidence,
    EvidenceRelationshipResult,
)

logger = logging.getLogger(__name__)

# Fraction of distinct claim terms a passage must contain before it is allowed
# to bear on the verdict at all. Keeps retrieval-candidate noise (topically
# adjacent but non-committal passages) from flipping a verdict.
DEFAULT_APPLICABILITY_THRESHOLD = 0.5

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Whole-token negation cues recognized after case/punctuation folding.
# Contractions arrive pre-split ("doesn't" -> {"doesn", "t"}), so the stems
# cover common apostrophe forms. Deliberately narrow: broad verb families such
# as "fails/failure/exclude" appear benignly in clinical text ("renal failure")
# and would manufacture false CONTRADICTS, so they are excluded.
NEGATION_CUES: frozenset[str] = frozenset(
    {
        "ain",
        "aren",
        "cannot",
        "couldn",
        "didn",
        "doesn",
        "don",
        "hadn",
        "hasn",
        "haven",
        "isn",
        "neither",
        "never",
        "no",
        "non",
        "none",
        "nor",
        "not",
        "shouldn",
        "unable",
        "unlikely",
        "wasn",
        "weren",
        "won",
        "wouldn",
        "without",
    }
)

# Deliberately conservative stopword snapshot: high-frequency grammatical words
# only. Independent copy of the retrieval stopword list (minus "no"/"not",
# which are negation cues and must survive filtering): this component's
# reproducibility must not shift when retrieval ranking tuning changes its own
# list. NEGATION_CUES and STOPWORDS are required to be disjoint — pinned by
# test.
STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "in",
        "is",
        "it",
        "its",
        "may",
        "of",
        "on",
        "or",
        "should",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
    }
)


def tokenize_with_negation(text: str) -> set[str]:
    """Case/punctuation-insensitive term extraction (stopwords removed).

    Unlike retrieval tokenization, negation cues are KEPT in the term set so
    polarity can be judged; they count toward coverage like any other term.
    """
    return {term for term in _TOKEN_RE.findall(text.casefold()) if term not in STOPWORDS}


def _is_negated(terms: set[str]) -> bool:
    """True when the term set contains at least one negation cue."""
    return bool(terms & NEGATION_CUES)


def _coverage(claim_terms: set[str], passage_terms: set[str]) -> float:
    """Fraction of distinct claim terms found in the passage. Deterministic."""
    if not claim_terms:
        return 0.0
    return len(claim_terms & passage_terms) / len(claim_terms)


class EvidenceRelationshipAssessor(ABC):
    """Contract for judging claim/evidence relationships.

    Any implementation — the offline default or a future model-backed one
    behind this same interface — returns relationship metadata only. Business
    logic stays testable without a live LLM by mocking this interface.
    """

    @abstractmethod
    def assess(self, claim: Claim, evidence: Sequence[Evidence]) -> EvidenceRelationshipResult:
        """Return the assessed relationship between claim and evidence. Never raises."""


class DeterministicRelationshipAssessor(EvidenceRelationshipAssessor):
    """Lexical-coverage + polarity assessment over supplied evidence. Offline only."""

    def __init__(self, applicability_threshold: float = DEFAULT_APPLICABILITY_THRESHOLD):
        if not 0.0 <= applicability_threshold <= 1.0:
            raise ValueError("applicability_threshold must be within [0.0, 1.0]")
        self._applicability_threshold = applicability_threshold

    def assess(self, claim: Claim, evidence: Sequence[Evidence]) -> EvidenceRelationshipResult:
        """Judge every passage against the claim. Never raises.

        Any unexpected error resolves to an explicit INSUFFICIENT result
        (succeeded=False) rather than propagating: a degraded assessment can
        only count as unsupported-by-evidence downstream, never as SUPPORTS.
        """
        try:
            return self._assess(claim, evidence)
        except Exception:  # noqa: BLE001 - deliberate fail-conservative with a reason
            logger.warning(
                "Evidence-relationship assessment failed; degrading to INSUFFICIENT",
                exc_info=True,
            )
            return EvidenceRelationshipResult(
                claim=claim,
                relationship=EvidenceRelationship.INSUFFICIENT,
                items=[],
                reasoning="assessment failed; degraded conservatively to INSUFFICIENT",
                confidence=0.0,
                succeeded=False,
                error_kind="assessment_failed",
            )

    def _assess(self, claim: Claim, evidence: Sequence[Evidence]) -> EvidenceRelationshipResult:
        claim_terms = tokenize_with_negation(claim.text)
        claim_negated = _is_negated(claim_terms)

        items: list[AssessedEvidence] = []
        for piece in evidence:
            piece_terms = tokenize_with_negation(piece.text)
            strength = _coverage(claim_terms, piece_terms)
            if strength < self._applicability_threshold:
                relationship = EvidenceRelationship.INSUFFICIENT
            elif _is_negated(piece_terms) != claim_negated:
                relationship = EvidenceRelationship.CONTRADICTS
            else:
                relationship = EvidenceRelationship.SUPPORTS
            items.append(
                AssessedEvidence(
                    source_id=piece.source_id,
                    text=piece.text,
                    relationship=relationship,
                    # Same provenance signal under both names, mirroring how
                    # RetrievedEvidence exposes score alongside confidence.
                    confidence=strength,
                    match_strength=strength,
                )
            )

        supporting = [item for item in items if item.relationship == EvidenceRelationship.SUPPORTS]
        contradicting = [
            item for item in items if item.relationship == EvidenceRelationship.CONTRADICTS
        ]
        applicable = supporting + contradicting

        if supporting and contradicting:
            aggregate = EvidenceRelationship.CONFLICTING
        elif supporting:
            aggregate = EvidenceRelationship.SUPPORTS
        elif contradicting:
            aggregate = EvidenceRelationship.CONTRADICTS
        else:
            aggregate = EvidenceRelationship.INSUFFICIENT

        applicable_strengths = [item.match_strength for item in applicable]
        confidence = (
            sum(applicable_strengths) / len(applicable_strengths) if applicable_strengths else 0.0
        )

        return EvidenceRelationshipResult(
            claim=claim,
            relationship=aggregate,
            items=items,
            reasoning=(
                f"{len(applicable)} of {len(items)} passages applicable "
                f"(threshold {self._applicability_threshold}); "
                f"{len(supporting)} support, {len(contradicting)} contradict"
            ),
            confidence=confidence,
        )


__all__ = [
    "DEFAULT_APPLICABILITY_THRESHOLD",
    "NEGATION_CUES",
    "RELATIONSHIP_VERSION",
    "STOPWORDS",
    "DeterministicRelationshipAssessor",
    "EvidenceRelationshipAssessor",
    "tokenize_with_negation",
]
