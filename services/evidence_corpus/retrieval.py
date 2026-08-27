"""Deterministic trusted-evidence retrieval (services/evidence_corpus).

Retrieves approved-source passages for queries or extracted claims. Fully
deterministic lexical scoring over the trusted corpus — no LLM call happens
here, ever — with strict reproducible ordering, so the same query against the
same corpus version always returns the same result.

STRUCTURAL CONSTRAINT: this component is incapable of producing a
PolicyAction or PolicyDecision. It returns RetrievalResult (evidence +
provenance only, exactly like TrajectoryAssessment). Failures degrade to an
empty-but-explicit result: with no evidence available, the later verification
stage can only resolve claims to UNVERIFIABLE — the conservative direction.
The exception is logged loudly so corpus outages are observable.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from domain.models import Claim
from services.evidence_corpus.models import (
    RETRIEVAL_VERSION,
    EvidenceDocument,
    RetrievalResult,
    RetrievedEvidence,
)
from services.evidence_corpus.store import (
    EvidenceStore,
    YamlFileEvidenceStore,
)

logger = logging.getLogger(__name__)

# Default corpus location follows the POLICY_PATH pattern: overridable via
# environment variable, falling back to the repository layout.
DEFAULT_EVIDENCE_CORPUS_PATH = (
    Path(__file__).resolve().parents[2] / "evidence" / "approved_sources.yaml"
)

# Very small, deliberately conservative stopword list: only high-frequency
# grammatical words whose presence in a claim carries no topical meaning.
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
        "no",
        "not",
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

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# How many ranked candidates one retrieval reports, and the lowest useful
# match score. Defaults keep retrieval generous (candidates, not verdicts);
# judging whether evidence actually supports a claim belongs to the later
# verification stage.
DEFAULT_MAX_RESULTS = 5
DEFAULT_MIN_SCORE = 0.0


def tokenize(text: str) -> set[str]:
    """Case/punctuation-insensitive topic-term extraction (stopwords removed)."""
    return {term for term in _TOKEN_RE.findall(text.casefold()) if term not in STOPWORDS}


class EvidenceRetriever:
    """Deterministic lexical retrieval over the trusted corpus. Evidence only."""

    def __init__(
        self,
        store: EvidenceStore | None = None,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
        min_score: float = DEFAULT_MIN_SCORE,
    ):
        if max_results < 1:
            raise ValueError("max_results must be at least 1")
        if not 0.0 <= min_score <= 1.0:
            raise ValueError("min_score must be within [0.0, 1.0]")
        self._store = store or YamlFileEvidenceStore(
            Path(os.getenv("EVIDENCE_CORPUS_PATH", str(DEFAULT_EVIDENCE_CORPUS_PATH)))
        )
        self._max_results = max_results
        self._min_score = min_score

    def retrieve(self, query: str) -> RetrievalResult:
        """Rank corpus passages against the query terms. Never raises."""
        try:
            corpus = self._store.load()
        except Exception:  # noqa: BLE001 - deliberate fail-conservative with a reason
            logger.warning(
                "Evidence corpus load failed; returning empty retrieval",
                exc_info=True,
            )
            return RetrievalResult(
                query=query,
                succeeded=False,
                error_kind="corpus_load_failed",
            )

        query_terms = tokenize(query)
        scored: list[tuple[float, EvidenceDocument]] = [
            (_match_score(query_terms, document_terms(document)), document)
            for document in corpus.documents
        ]
        # Strict deterministic ordering: descending score, ties broken by
        # source_id — identical corpus + query always yields identical output.
        ordered = sorted(
            (item for item in scored if item[0] > 0.0 and item[0] >= self._min_score),
            key=lambda item: (-item[0], item[1].source_id),
        )[: self._max_results]

        return RetrievalResult(
            query=query,
            matches=[
                RetrievedEvidence(
                    source_id=document.source_id,
                    text=document.text,
                    title=document.title,
                    confidence=score,
                    score=score,
                )
                for score, document in ordered
            ],
            corpus_version=corpus.version,
            total_candidates=len(corpus.documents),
        )

    def retrieve_for_claim(self, claim: Claim) -> RetrievalResult:
        """Convenience alias so the later verification stage never re-tokenizes."""
        return self.retrieve(claim.text)


def document_terms(document: EvidenceDocument) -> set[str]:
    """Searchable term set for one passage: title + text + curated topics."""
    return tokenize(f"{document.title} {document.text} {' '.join(document.topics)}")


def _match_score(query_terms: set[str], document_terms_set: set[str]) -> float:
    """Fraction of distinct query terms found in the passage. Deterministic."""
    if not query_terms:
        return 0.0
    return len(query_terms & document_terms_set) / len(query_terms)


__all__ = [
    "DEFAULT_EVIDENCE_CORPUS_PATH",
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_MIN_SCORE",
    "STOPWORDS",
    "EvidenceRetriever",
    "RETRIEVAL_VERSION",
    "tokenize",
]
