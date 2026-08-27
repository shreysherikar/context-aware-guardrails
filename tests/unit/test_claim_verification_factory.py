"""Unit tests for the claim/evidence verification factory config contract.

The scenario suite injects fakes via monkeypatched module attributes, so these
tests pin the PUBLIC configuration path that actually wires the stage into the
API at import time (apps/api/main.py: get_claim_verifier()):

- unset/empty CLAIM_VERIFICATION_PROVIDER -> stage off (None), keeping existing
  behavior unchanged unless explicitly enabled
- "deterministic" -> a working GeneratedTextVerifier built lazily (constructing
  it must not read the corpus file or touch the network)
- any unknown value fails loudly at startup instead of silently disabling
"""

import pytest

from services.claim_verification.factory import get_claim_verifier


def test_provider_unset_means_the_stage_is_off(monkeypatch):
    monkeypatch.delenv("CLAIM_VERIFICATION_PROVIDER", raising=False)

    assert get_claim_verifier() is None


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_provider_value_also_disables_the_stage(monkeypatch, value):
    monkeypatch.setenv("CLAIM_VERIFICATION_PROVIDER", value)

    assert get_claim_verifier() is None


def test_deterministic_provider_builds_a_working_offline_verifier(monkeypatch):
    monkeypatch.setenv("CLAIM_VERIFICATION_PROVIDER", "deterministic")

    verifier = get_claim_verifier()

    from services.claim_extraction.extractor import (
        ClaimExtractor,
        DeterministicClaimExtractor,
    )
    from services.claim_verification.service import GeneratedTextVerifier
    from services.evidence_corpus.retrieval import EvidenceRetriever
    from services.evidence_relationship.assessor import (
        EvidenceRelationshipAssessor,
    )

    assert isinstance(verifier, GeneratedTextVerifier)
    # Composition is intact: all three offline stages behind their interfaces,
    # so business logic stays mockable per repo testing rules.
    assert isinstance(verifier._extractor, ClaimExtractor)
    assert isinstance(verifier._extractor, DeterministicClaimExtractor)
    assert isinstance(verifier._retriever, EvidenceRetriever)
    assert isinstance(verifier._assessor, EvidenceRelationshipAssessor)


def test_deterministic_constructor_does_not_read_corpus_or_network(monkeypatch, tmp_path):
    """Construction must be side-effect free: run it with the default corpus
    location repointed at a nonexistent file and prove nothing breaks."""
    monkeypatch.setenv("CLAIM_VERIFICATION_PROVIDER", "deterministic")
    monkeypatch.setenv("EVIDENCE_CORPUS_PATH", str(tmp_path / "missing.yaml"))

    verifier = get_claim_verifier()

    assert verifier is not None  # loading happens lazily per verification call


@pytest.mark.parametrize("value", ["groq", "magic"])
def test_unknown_values_fail_loudly_at_startup(monkeypatch, value):
    monkeypatch.setenv("CLAIM_VERIFICATION_PROVIDER", value)

    with pytest.raises(ValueError) as excinfo:
        get_claim_verifier()

    assert "CLAIM_VERIFICATION_PROVIDER" in str(excinfo.value)
