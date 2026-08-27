"""Unit tests for the evidence-relationship assessor.

Pins the guarantees of the relationship stage between trusted-corpus retrieval
and any later verification/policy consumption:

- the four-value vocabulary: SUPPORTS / CONTRADICTS / INSUFFICIENT / CONFLICTING
- structural constraint: nothing here can carry policy authority (instance
  attributes, declared model fields, AND AST-level identifiers including
  imports — so PolicyAction/PolicyDecision can never enter this package)
- fail-closed construction (omitted verdict or claim raises) and
  fail-conservative degradation (internal errors resolve to INSUFFICIENT,
  never to SUPPORTS)
- deterministic lexical behaviour: coverage gate, polarity disagreement,
  conflicting mixtures, stable input ordering, reproducible repeated calls
- the interface is mockable: business logic runs with zero live-LLM/network
  use, per the repo's testing rules
"""

import ast
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

import services.evidence_relationship as er_package
import services.evidence_relationship.assessor as er_assessor
import services.evidence_relationship.models as er_models
from domain.enums import EvidenceRelationship
from domain.models import Claim, Evidence
from services.evidence_relationship.assessor import (
    DEFAULT_APPLICABILITY_THRESHOLD,
    NEGATION_CUES,
    STOPWORDS,
    DeterministicRelationshipAssessor,
    EvidenceRelationshipAssessor,
    tokenize_with_negation,
)
from services.evidence_relationship.models import (
    RELATIONSHIP_VERSION,
    AssessedEvidence,
    EvidenceRelationshipResult,
)

_FORBIDDEN_AUTHORITY_FIELDS = frozenset({"action", "decision", "policy_id", "policy_version"})
# Field-name clashes AND class-name references both count as authority leaks.
_FORBIDDEN_AUTHORITY_IDENTIFIERS = _FORBIDDEN_AUTHORITY_FIELDS | {
    "PolicyAction",
    "PolicyDecision",
}
_PACKAGE_MODULES = (er_package, er_models, er_assessor)

_AFFIRMING = "Drug X treats condition Y"
_NEGATING = "Drug X does not cure condition Y"
_CLAIM_TEXT = "Drug X cures condition Y"


def _claim(text: str = _CLAIM_TEXT) -> Claim:
    return Claim(text=text, confidence=0.9)


def _evidence(text: str = _AFFIRMING, source_id: str = "SRC-A") -> Evidence:
    return Evidence(source_id=source_id, text=text, confidence=0.8)


def _assessor(
    threshold: float = DEFAULT_APPLICABILITY_THRESHOLD,
) -> DeterministicRelationshipAssessor:
    return DeterministicRelationshipAssessor(threshold)


def _failed(claim: Claim | None = None) -> EvidenceRelationshipResult:
    return EvidenceRelationshipResult(
        claim=claim or _claim(),
        relationship=EvidenceRelationship.INSUFFICIENT,
        succeeded=False,
        error_kind="assessment_failed",
    )


# --- structural constraint: relationships only, never a decision ---------------


def test_no_instance_carries_policy_authority_attributes():
    supported = _assessor().assess(_claim(), [_evidence()])
    samples: list[object] = [
        supported,
        _failed(),
        AssessedEvidence(source_id="s", text="t", relationship=EvidenceRelationship.SUPPORTS),
    ]
    for sample in samples:
        for field in _FORBIDDEN_AUTHORITY_FIELDS:
            assert not hasattr(sample, field)


def test_declared_model_fields_can_never_gain_authority_fields():
    for model in (AssessedEvidence, EvidenceRelationshipResult):
        assert _FORBIDDEN_AUTHORITY_FIELDS.isdisjoint(model.model_fields), model.__name__


def test_package_modules_never_reference_policy_authority_identifiers():
    def identifiers(module_path: str) -> set[str]:
        tree = ast.parse(Path(module_path).read_text(encoding="utf-8"))
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.rsplit(".", 1)[-1])
                found.update(alias.name for alias in node.names)
        return found

    for module in _PACKAGE_MODULES:
        clash = identifiers(str(module.__file__)) & _FORBIDDEN_AUTHORITY_IDENTIFIERS
        assert not clash, f"{module.__name__} references {clash}"


def test_enum_has_exactly_the_four_relationship_values():
    assert {value.value for value in EvidenceRelationship} == {
        "SUPPORTS",
        "CONTRADICTS",
        "INSUFFICIENT",
        "CONFLICTING",
    }


# --- fail-closed construction ---------------------------------------------------


def test_omitted_relationship_is_a_construction_error_not_a_silent_default():
    # A missing verdict must raise, never resolve to something that could be
    # misread as SUPPORTS downstream.
    with pytest.raises(ValidationError):
        EvidenceRelationshipResult(claim=_claim())


def test_omitted_claim_is_a_construction_error_so_provenance_cannot_be_lost():
    with pytest.raises(ValidationError):
        EvidenceRelationshipResult(relationship=EvidenceRelationship.SUPPORTS)


def test_policy_action_literals_cannot_be_squeezed_into_the_vocabulary():
    # ALLOW/BLOCK are policy values, not relationships; the enum-typed field
    # must refuse them rather than coerce or pass through.
    with pytest.raises(ValidationError):
        EvidenceRelationshipResult.model_validate(
            {"claim": {"text": _CLAIM_TEXT}, "relationship": "ALLOW"}
        )


# (model, builder, confidence reader) — the Result reads .confidence while the
# item records its signal as .match_strength; each must stay inside [0, 1].
_CONFIDENCE_BOUND_CASES = [
    (
        "EvidenceRelationshipResult",
        lambda confidence: EvidenceRelationshipResult(
            claim=_claim(),
            relationship=EvidenceRelationship.CONFLICTING,
            confidence=confidence,
        ),
        lambda result: result.confidence,
    ),
    (
        "AssessedEvidence",
        lambda confidence: AssessedEvidence(
            source_id="s",
            text="t",
            relationship=EvidenceRelationship.SUPPORTS,
            match_strength=confidence,
        ),
        lambda assessed: assessed.match_strength,
    ),
]


@pytest.mark.parametrize("confidence", [-0.1, -1.0, 1.0001])
def test_out_of_range_confidence_is_rejected(confidence):
    for _, build, _reader in _CONFIDENCE_BOUND_CASES:
        with pytest.raises(ValidationError):
            build(confidence)


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_valid_confidences_are_accepted_unchanged(confidence):
    for _, build, reader in _CONFIDENCE_BOUND_CASES:
        assert reader(build(confidence)) == confidence


# --- auditability ----------------------------------------------------------------


def test_results_record_the_assessor_component_version():
    result = EvidenceRelationshipResult(
        claim=_claim(),
        relationship=EvidenceRelationship.INSUFFICIENT,
    )

    assert result.assessor_version == RELATIONSHIP_VERSION


def test_round_trip_serialization_preserves_the_full_structure():
    result = _assessor().assess(
        _claim(),
        [_evidence(_AFFIRMING, "SRC-A"), _evidence(_NEGATING, "SRC-B")],
    )

    restored = EvidenceRelationshipResult.model_validate(result.model_dump())

    assert restored == result
    assert [item.source_id for item in restored.items] == ["SRC-A", "SRC-B"]


# --- deterministic behaviour: the four relationships ------------------------------


def test_affirming_claim_with_affirming_applicable_evidence_supports():
    result = _assessor().assess(_claim(), [_evidence()])

    assert result.succeeded is True
    assert result.error_kind is None
    assert result.relationship == EvidenceRelationship.SUPPORTS
    item = result.items[0]
    assert item.relationship == EvidenceRelationship.SUPPORTS
    assert item.match_strength == pytest.approx(0.8)
    assert result.confidence == pytest.approx(0.8)
    assert result.reasoning.startswith("1 of 1 passages applicable")


def test_affirming_claim_against_negated_passage_contradicts():
    result = _assessor().assess(_claim(), [_evidence(_NEGATING)])

    assert result.relationship == EvidenceRelationship.CONTRADICTS
    assert result.items[0].relationship == EvidenceRelationship.CONTRADICTS


def test_negated_claim_against_affirming_passage_contradicts():
    # Polarity disagreement counts in both directions (coverage 4/6 >= 0.5).
    result = _assessor(0.5).assess(
        _claim("Drug X does not cure condition Y"),
        [_evidence()],
    )

    assert result.relationship == EvidenceRelationship.CONTRADICTS


def test_two_negated_texts_agree_and_support():
    # Double negative reads as affirmation, deterministically.
    result = _assessor().assess(
        _claim("Drug X does not cure condition Y"),
        [_evidence("Drug X does not treat condition Y")],
    )

    assert result.relationship == EvidenceRelationship.SUPPORTS
    assert result.items[0].relationship == EvidenceRelationship.SUPPORTS


def test_mixed_supporting_and_contradicting_passages_conflict():
    result = _assessor().assess(
        _claim(),
        [_evidence(_AFFIRMING, "SRC-A"), _evidence(_NEGATING, "SRC-B")],
    )

    assert result.relationship == EvidenceRelationship.CONFLICTING
    assert result.reasoning.startswith("2 of 2 passages applicable")
    assert {item.relationship for item in result.items} == {
        EvidenceRelationship.SUPPORTS,
        EvidenceRelationship.CONTRADICTS,
    }


def test_reverse_order_of_passages_still_conflicts():
    result = _assessor().assess(
        _claim(),
        [_evidence(_NEGATING, "SRC-B"), _evidence(_AFFIRMING, "SRC-A")],
    )

    assert result.relationship == EvidenceRelationship.CONFLICTING


# --- conservative insufficiency ---------------------------------------------------


def test_no_evidence_at_all_is_insufficient_never_supported():
    result = _assessor().assess(_claim(), [])

    assert result.succeeded is True
    assert result.relationship == EvidenceRelationship.INSUFFICIENT
    assert result.items == []
    assert result.confidence == 0.0


def test_only_off_topic_passages_are_insufficient():
    result = _assessor().assess(
        _claim(),
        [_evidence("Quarterly revenue forecast meeting notes", "FIN-1")],
    )

    assert result.relationship == EvidenceRelationship.INSUFFICIENT
    assert result.items[0].relationship == EvidenceRelationship.INSUFFICIENT
    assert result.items[0].match_strength == 0.0
    assert result.confidence == 0.0


@pytest.mark.parametrize("degenerate_text", ["", "The of and can it may", "!?."])
def test_degenerate_claims_degrade_to_insufficient(degenerate_text):
    result = _assessor().assess(Claim(text=degenerate_text), [_evidence()])

    assert result.relationship == EvidenceRelationship.INSUFFICIENT
    assert all(item.relationship == EvidenceRelationship.INSUFFICIENT for item in result.items)


def test_every_produced_relationship_is_a_declared_value():
    assessor = _assessor()
    results = [
        assessor.assess(_claim(), [_evidence()]),
        assessor.assess(_claim(), [_evidence(_NEGATING)]),
        assessor.assess(_claim(), [_evidence(_AFFIRMING), _evidence(_NEGATING)]),
        assessor.assess(_claim(), []),
        _failed(),
    ]

    for result in results:
        assert result.relationship in set(EvidenceRelationship)


# --- applicability gate ------------------------------------------------------------


def test_threshold_boundary_is_inclusive():
    # Coverage 3/4 == 0.75 exactly: at the gate the passage counts (>=), above
    # the gate it does not.
    partial = _evidence("alpha beta gamma note")

    at_gate = _assessor(0.75).assess(_claim("alpha beta gamma delta"), [partial])
    above_gate = _assessor(0.9).assess(_claim("alpha beta gamma delta"), [partial])

    assert at_gate.relationship == EvidenceRelationship.SUPPORTS
    assert above_gate.relationship == EvidenceRelationship.INSUFFICIENT


def test_threshold_of_one_demands_full_term_coverage():
    complete = _assessor(1.0).assess(
        _claim("alpha beta gamma delta"),
        [_evidence("delta alpha extras beta gamma")],
    )
    incomplete = _assessor(1.0).assess(
        _claim("alpha beta gamma delta"),
        [_evidence("alpha beta gamma nothing more")],
    )

    assert complete.relationship == EvidenceRelationship.SUPPORTS
    assert incomplete.relationship == EvidenceRelationship.INSUFFICIENT


@pytest.mark.parametrize("bad_threshold", [-0.1, 1.0001, -1.0])
def test_out_of_range_threshold_fails_fast_at_construction(bad_threshold):
    with pytest.raises(ValueError):
        DeterministicRelationshipAssessor(bad_threshold)


def test_configured_threshold_is_recorded_in_the_reasoning():
    result = _assessor(0.9).assess(_claim(), [_evidence()])

    assert "threshold 0.9" in result.reasoning


# --- determinism and reproducibility ------------------------------------------------


def test_input_ordering_is_preserved_verbatim():
    evidence = [_evidence(_NEGATING, "B"), _evidence(_AFFIRMING, "A")]

    result = _assessor().assess(_claim(), evidence)

    assert [item.source_id for item in result.items] == ["B", "A"]


def test_repeated_calls_are_reproducible_exactly():
    assessor = _assessor()

    first = assessor.assess(_claim(), [_evidence(), _evidence(_NEGATING, "SRC-B")])
    second = assessor.assess(_claim(), [_evidence(), _evidence(_NEGATING, "SRC-B")])

    assert first == second
    assert first.model_dump() == second.model_dump()


# --- conservative failure handling ---------------------------------------------------


class _ExplodingEvidence:
    """Duck-typed evidence whose text access blows up, like a broken store."""

    source_id = "BOOM"

    @property
    def text(self) -> str:
        raise RuntimeError("evidence backend down")


def test_internal_failures_degrade_to_insufficient_never_supports():
    result = _assessor().assess(_claim(), [_ExplodingEvidence()])  # type: ignore[list-item]

    assert result.succeeded is False
    assert result.error_kind == "assessment_failed"
    assert result.relationship == EvidenceRelationship.INSUFFICIENT
    assert result.items == []
    assert result.confidence == 0.0
    for field in _FORBIDDEN_AUTHORITY_FIELDS:
        assert not hasattr(result, field)


# --- mockable interface: business logic without a live model -------------------------


class _FakeModelBackedAssessor(EvidenceRelationshipAssessor):
    """Stands in for any future model-backed implementation; zero network use."""

    def __init__(self, canned: EvidenceRelationshipResult):
        self._canned = canned
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def assess(self, claim: Claim, evidence: Sequence[Evidence]) -> EvidenceRelationshipResult:
        self.calls.append((claim.text, tuple(piece.source_id for piece in evidence)))
        return self._canned


def test_interface_admits_a_mock_implementation_without_any_live_model_call():
    canned = EvidenceRelationshipResult(
        claim=_claim(),
        relationship=EvidenceRelationship.CONFLICTING,
        succeeded=True,
    )
    fake = _FakeModelBackedAssessor(canned)

    assert isinstance(fake, EvidenceRelationshipAssessor)

    # A consumer written against the ABC gets exactly the canned verdict.
    result = fake.assess(_claim(), [_evidence("whatever", "SRC-A")])

    assert result is canned
    assert fake.calls == [(_CLAIM_TEXT, ("SRC-A",))]


def test_default_implementation_is_the_deterministic_offline_one():
    # The shipped assessor must never need a model: same input twice is
    # identical and requires no network (exercised implicitly everywhere else).
    assert isinstance(_assessor(), DeterministicRelationshipAssessor)


# --- tokenizer -----------------------------------------------------------------------


def test_tokenize_keeps_negation_cues_and_drops_grammar_words():
    tokens = tokenize_with_negation("No DOSE adjustment!")

    assert tokens == {"no", "dose", "adjustment"}
    assert "the" not in tokenize_with_negation("the dose")
    assert tokenize_with_negation("") == set()


def test_contraction_stems_survive_tokenization_so_polarity_is_detectable():
    assert "doesn" in tokenize_with_negation("Doesn't work")
    assert "isn" in tokenize_with_negation("It isn't effective")


def test_stopwords_and_negation_cues_are_disjoint_by_contract():
    # If a cue ever leaked into the stopword list, polarity detection would
    # silently break; this invariant is load-bearing for CONTRADICTS.
    assert NEGATION_CUES.isdisjoint(STOPWORDS)
