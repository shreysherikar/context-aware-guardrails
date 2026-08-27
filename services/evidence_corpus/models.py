"""Evidence-corpus contracts — trusted approved-source material.

The corpus is the trusted side of claim/evidence verification: curated,
version-controlled approved sources that generated claims are later checked
against. This module holds the data contracts for storing and retrieving that
material only.

STRUCTURAL CONSTRAINT: nothing in this package produces, carries, or implies
a PolicyAction or a PolicyDecision. Retrieval returns evidence/provenance
only; verifying claims against it and deciding what happens are separate,
later stages (only the PolicyEngine decides anything).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field, field_validator

from domain.models import Evidence

# Version of the retrieval logic itself (recorded on every result so audits
# remain reproducible even if ranking evolves). Mirrors SANITIZER_VERSION.
RETRIEVAL_VERSION = "1.0.0"


class EvidenceDocument(BaseModel):
    """One curated passage from an approved source, as stored in the corpus.

    ``topics`` are lowercase index keywords used by the deterministic
    retriever. They are curation metadata, not policy conditions.
    """

    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    topics: list[str] = Field(default_factory=list)


class EvidenceCorpus(BaseModel):
    """A complete, immutable snapshot of the trusted corpus.

    ``version`` identifies the snapshot so any future verification outcome can
    name exactly which corpus revision grounded it (reproducibility). Source
    IDs must be unique: a repeated ID would make provenance ambiguous.
    """

    version: str = Field(min_length=1)
    documents: list[EvidenceDocument] = Field(default_factory=list)

    @field_validator("documents")
    @classmethod
    def _source_ids_must_be_unique(
        cls, documents: list[EvidenceDocument]
    ) -> list[EvidenceDocument]:
        seen: set[str] = set()
        for document in documents:
            if document.source_id in seen:
                raise ValueError(f"duplicate source_id in corpus: {document.source_id!r}")
            seen.add(document.source_id)
        return documents


class RetrievedEvidence(Evidence):
    """One corpus passage returned by retrieval, with match provenance.

    Extends the shared domain Evidence contract (source_id / text /
    confidence). ``confidence`` carries the retrieval match strength (fraction
    of distinct query terms found in the passage, 0..1) — it is a search
    signal for the later verification stage, never a policy weight.
    """

    title: str | None = None
    score: float = Field(ge=0.0, le=1.0, default=0.0)


class RetrievalResult(BaseModel):
    """Structured output of one retrieval against the trusted corpus.

    Modeled on the LLMResult/OutputGuardrailResult pattern: minimal signals
    (succeeded / error_kind) plus the payload. On failure, matches stay empty
    and error_kind says why — which keeps the downstream verification stage
    conservative, because absence of evidence can only ever resolve a claim
    to UNVERIFIABLE, never to SUPPORTED.
    """

    # Fields no member of this package may ever grow (structural guard).
    FORBIDDEN_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"action", "decision", "policy_id", "policy_version"}
    )

    query: str
    matches: list[RetrievedEvidence] = Field(default_factory=list)
    corpus_version: str | None = None
    total_candidates: int = 0
    succeeded: bool = True
    error_kind: str | None = None
    retriever_version: str = RETRIEVAL_VERSION
