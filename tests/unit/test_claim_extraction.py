"""Unit tests for the offline claim extractor (services/claim_extraction).

Pins the guarantees of the pipeline's first stage:

- deterministic sentence segmentation: stable order, reproducible repeat calls
- line breaks act as claim boundaries; trivial/empty fragments are skipped
- exact-duplicate sentences are deduplicated (one assessment per assertion)
- extraction is bounded by ``max_claims`` with deterministic truncation
- extracted records are plain Claim values carrying uniform confidence
- the interface admits mock implementations without any live model
- internal failures raise an explicit ClaimExtractionError instead of returning
  an empty-looking success: an empty result would let downstream verification
  pass vacuously (fail closed).
"""

import pytest

from domain.models import Claim
from services.claim_extraction.extractor import (
    CLAIM_EXTRACTION_VERSION,
    DEFAULT_CLAIM_CONFIDENCE,
    ClaimExtractionError,
    ClaimExtractor,
    DeterministicClaimExtractor,
)


def test_sentences_are_extracted_in_stable_order():
    text = "Drug X treats condition Y. It is taken once daily with food."

    claims = DeterministicClaimExtractor().extract(text)

    assert [c.text for c in claims] == [
        "Drug X treats condition Y.",
        "It is taken once daily with food.",
    ]


def test_repeated_calls_are_reproducible_exactly():
    extractor = DeterministicClaimExtractor()
    text = "First verifiable sentence here.\nSecond verifiable sentence here!"

    assert extractor.extract(text) == extractor.extract(text)
    assert CLAIM_EXTRACTION_VERSION == "1.0.0"


def test_line_breaks_act_as_claim_boundaries():
    text = "- GLYXTRA maximum daily dose is 2000 mg\n- Taken once daily"

    texts = [c.text for c in DeterministicClaimExtractor().extract(text)]

    assert texts == ["GLYXTRA maximum daily dose is 2000 mg", "Taken once daily"]


def test_exact_duplicate_sentences_are_deduplicated():
    text = "Drug X treats condition Y. Drug X treats condition Y."

    texts = [c.text for c in DeterministicClaimExtractor().extract(text)]

    assert texts == ["Drug X treats condition Y."]


def test_trivial_and_empty_fragments_are_skipped():
    assert DeterministicClaimExtractor().extract("") == []

    text = "   \n ?!  \n A real verifiable sentence lives here."

    assert [c.text for c in DeterministicClaimExtractor().extract(text)] == [
        "A real verifiable sentence lives here."
    ]


def test_extraction_is_bounded_by_max_claims_in_input_order():
    extractor = DeterministicClaimExtractor(max_claims=2)
    text = "Claim number one sentence. Claim number two sentence. Claim number three sentence."

    texts = [c.text for c in extractor.extract(text)]

    assert texts == ["Claim number one sentence.", "Claim number two sentence."]


def test_invalid_constructor_arguments_fail_fast():
    with pytest.raises(ValueError):
        DeterministicClaimExtractor(max_claims=0)


def test_claims_carry_uniform_confidence_and_only_safe_fields():
    claims = DeterministicClaimExtractor().extract("A verifiable statement about dosing.")

    assert claims
    assert all(isinstance(c, Claim) for c in claims)
    assert all(c.confidence == DEFAULT_CLAIM_CONFIDENCE for c in claims)


class _FakeExtractor(ClaimExtractor):
    """Stands in for any future model-backed implementation; zero network use."""

    def __init__(self):
        self.calls: list[str] = []

    def extract(self, generated_text: str) -> list[Claim]:
        self.calls.append(generated_text)
        return [Claim(text="canned claim", confidence=1.0)]


def test_interface_admits_a_mock_implementation_without_any_live_model_call():
    fake = _FakeExtractor()

    assert isinstance(fake, ClaimExtractor)
    assert [c.text for c in fake.extract("anything")] == ["canned claim"]
    assert fake.calls == ["anything"]


@pytest.mark.parametrize("bad_input", [None, 42, ["list"], {"dict": 1}])
def test_internal_failures_raise_an_explicit_error_never_a_silent_success(bad_input):
    # Extractor exceptions are converted to ClaimExtractionError by design: the
    # verification orchestrator turns them into a conservative UNVERFIABLE
    # verdict (REVIEW) instead of an empty (vacuously supported) aggregate.
    with pytest.raises(ClaimExtractionError):
        DeterministicClaimExtractor().extract(bad_input)  # type: ignore[arg-type]
