"""Unit tests for the claim/evidence verification domain contracts.

Pins the minimal four-model shape (Claim, Evidence, EvidenceAssessment,
ClaimEvidenceAssessment):

- structural constraint: none of them can carry policy authority
- an omitted verification status fails closed at construction time
- confidence fields stay inside [0.0, 1.0]
- the aggregate's derived views can never desync from its detail list, and
  anything that is not SUPPORTED counts as unverified (including statuses
  added to the enum later)
- serialization round-trips losslessly so assessments stay auditable and
  reproducible
"""

import pytest
from pydantic import ValidationError

from domain.enums import VerificationStatus
from domain.models import (
    Claim,
    ClaimEvidenceAssessment,
    Evidence,
    EvidenceAssessment,
)

_POLICY_AUTHORITY_FIELDS = ["action", "policy_id", "policy_version"]


def _claim(text: str = "Drug X cures condition Y") -> Claim:
    return Claim(text=text, confidence=0.9)


def _evidence(source_id: str = "approved-source-1") -> Evidence:
    return Evidence(source_id=source_id, text="Drug X treats condition Y", confidence=0.8)


def _assessment(
    status: VerificationStatus, text: str = "Drug X cures condition Y"
) -> EvidenceAssessment:
    return EvidenceAssessment(claim=_claim(text), status=status, reasoning="checked")


_CONFIDENCE_MODELS = [
    ("Claim", lambda confidence: Claim(text="t", confidence=confidence)),
    ("Evidence", lambda confidence: Evidence(source_id="s", text="t", confidence=confidence)),
    (
        "EvidenceAssessment",
        lambda confidence: EvidenceAssessment(
            claim=_claim(), status=VerificationStatus.UNVERIFIABLE, confidence=confidence
        ),
    ),
]


# --- structural constraint: evidence only, never a decision -------------------


def test_no_model_carries_policy_authority():
    samples = [
        _claim(),
        _evidence(),
        _assessment(VerificationStatus.UNSUPPORTED),
        ClaimEvidenceAssessment(),
    ]
    for sample in samples:
        for field in _POLICY_AUTHORITY_FIELDS:
            assert not hasattr(sample, field)


# --- fail-closed construction --------------------------------------------------


def test_omitted_status_is_a_construction_error_not_a_silent_default():
    # A missing verdict must raise, never resolve to something that could be
    # misread as SUPPORTED downstream.
    with pytest.raises(ValidationError):
        EvidenceAssessment(claim=_claim())


def test_unverifiable_is_distinct_from_unsupported():
    # "no applicable approved source found" is not "contradicted by a source";
    # collapsing them would hide whether a claim was checked at all.
    assert _assessment(VerificationStatus.UNVERIFIABLE).status is not (
        _assessment(VerificationStatus.UNSUPPORTED).status
    )


def test_enum_has_exactly_the_three_verdict_values_as_strings():
    assert {status.value for status in VerificationStatus} == {
        "SUPPORTED",
        "UNSUPPORTED",
        "UNVERIFIABLE",
    }


# --- confidence bounds ---------------------------------------------------------


@pytest.mark.parametrize("confidence", [-0.1, -1.0, 1.0001])
def test_out_of_range_confidence_is_rejected(confidence):
    for _, factory in _CONFIDENCE_MODELS:
        with pytest.raises(ValidationError):
            factory(confidence)


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_valid_confidences_are_accepted_unchanged(confidence):
    for _, factory in _CONFIDENCE_MODELS:
        assert factory(confidence).confidence == confidence


# --- aggregate derived views ---------------------------------------------------


def test_no_claims_is_vacuously_all_supported():
    # Mirrors OutputAssessment: an empty unverified set is not itself a finding.
    aggregate = ClaimEvidenceAssessment()

    assert aggregate.assessments == []
    assert aggregate.unverified_claims == []
    assert aggregate.all_supported is True


def test_unverified_claims_lists_exactly_the_non_supported_in_order():
    aggregate = ClaimEvidenceAssessment(
        assessments=[
            _assessment(VerificationStatus.UNSUPPORTED, "unsupported claim"),
            _assessment(VerificationStatus.SUPPORTED, "supported claim"),
            _assessment(VerificationStatus.UNVERIFIABLE, "unverifiable claim"),
        ]
    )

    assert aggregate.unverified_claims == ["unsupported claim", "unverifiable claim"]
    assert aggregate.all_supported is False


@pytest.mark.parametrize("status", list(VerificationStatus))
def test_any_non_supported_status_resolves_conservatively(status):
    # Adding a status to the enum later cannot accidentally permit a claim:
    # only exact equality with SUPPORTED clears the unverified list.
    aggregate = ClaimEvidenceAssessment(assessments=[_assessment(status)])

    if status == VerificationStatus.SUPPORTED:
        assert aggregate.unverified_claims == []
        assert aggregate.all_supported is True
    else:
        assert aggregate.unverified_claims == ["Drug X cures condition Y"]
        assert aggregate.all_supported is False


def test_derived_views_follow_detail_edits_instead_of_desyncing():
    # unverified_claims is computed from assessments on every access, so it is
    # impossible for the short summary to contradict the per-claim detail.
    assessment = _assessment(VerificationStatus.UNSUPPORTED)
    aggregate = ClaimEvidenceAssessment(assessments=[assessment])

    assert aggregate.unverified_claims == [assessment.claim.text]

    assessment.status = VerificationStatus.SUPPORTED

    assert aggregate.unverified_claims == []
    assert aggregate.all_supported is True


# --- auditability --------------------------------------------------------------


def test_round_trip_serialization_preserves_the_full_structure():
    # Decisions must be reproducible from serialized evidence alone.
    aggregate = ClaimEvidenceAssessment(
        assessments=[
            EvidenceAssessment(
                claim=_claim(),
                status=VerificationStatus.UNSUPPORTED,
                supporting_evidence=[_evidence(), _evidence("approved-source-2")],
                reasoning="contradicted",
                confidence=0.95,
            ),
            _assessment(VerificationStatus.UNVERIFIABLE),
        ]
    )

    restored = ClaimEvidenceAssessment.model_validate(aggregate.model_dump())

    assert restored == aggregate
    assert restored.unverified_claims == aggregate.unverified_claims
    assert restored.assessments[0].supporting_evidence[1].source_id == "approved-source-2"
