"""Evidence-relationship contracts — structured relationship metadata only.

The relationship stage sits between trusted-corpus retrieval and any later
verification/consumption stage: retrieval finds candidate passages, this
stage judges how they relate to one claim (SUPPORTS / CONTRADICTS /
INSUFFICIENT / CONFLICTING).

STRUCTURAL CONSTRAINT: nothing in this package produces, carries, or implies
a PolicyAction or a PolicyDecision. Results carry relationships and
provenance only; deciding what happens to unsupported claims belongs solely
to the deterministic PolicyEngine (services/policy_engine).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from domain.enums import EvidenceRelationship
from domain.models import Claim, Evidence

# Version of the relationship-assessment logic itself (recorded on every
# result so audits stay reproducible even if the algorithm evolves). Mirrors
# RETRIEVAL_VERSION. 1.1.0: clause-local negation scoping + formatting
# normalization replaced whole-text polarity (see assessor.py history note).
RELATIONSHIP_VERSION = "1.1.0"


class AssessedEvidence(Evidence):
    """One evaluated passage plus the relationship judged between it and the claim.

    Extends the shared domain Evidence contract (source_id / text /
    confidence). ``match_strength`` records the lexical coverage (fraction of
    distinct claim terms found in the passage, 0..1) that drove the
    relationship — a search signal for auditors, never a policy weight.
    ``relationship`` is required with no default: an omitted verdict fails at
    construction time instead of silently resolving to something that could be
    misread downstream (fail closed).
    """

    relationship: EvidenceRelationship
    match_strength: float = Field(ge=0.0, le=1.0, default=0.0)


class EvidenceRelationshipResult(BaseModel):
    """Structured output of one relationship assessment. Relationship + provenance only.

    Modeled on RetrievalResult / LLMResult: minimal failure signals
    (succeeded / error_kind) plus the payload. On failure the relationship is
    INSUFFICIENT — the conservative direction, because degraded assessment can
    only ever count as unsupported-by-evidence, never as SUPPORTS.
    """

    # Fields no member of this package may ever grow (structural guard).
    FORBIDDEN_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"action", "decision", "policy_id", "policy_version"}
    )

    claim: Claim
    relationship: EvidenceRelationship
    items: list[AssessedEvidence] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    succeeded: bool = True
    error_kind: str | None = None
    assessor_version: str = RELATIONSHIP_VERSION
