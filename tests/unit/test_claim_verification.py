"""Unit tests for the claim/evidence verification orchestrator.

Pins the guarantees of the stage that stitches extraction -> trusted-corpus
retrieval -> relationship assessment into one domain ClaimEvidenceAssessment:

- structuration only: nothing here can carry or reference policy authority
  (instance attributes AND module-source identifiers, per sibling suites)
- conservative mapping SUPPORTS->SUPPORTED, CONTRADICTS/CONFLICTING->UNSUPPORTED,
  INSUFFICIENT->UNVERIFIABLE, so every non-agreeing outcome counts as unverified
- supporting evidence records exactly the agreeing passages with provenance
- retrieval provenance (corpus version, component versions) is carried through
- empty generations yield a clean vacuous result rather than a finding
- NEVER RAISES: internal failures across any stage degrade to succeeded=False
  with a synthetic UNVERIFIABLE claim whose aggregate stays unverified —
  a broken verifier routes responses to REVIEW, never to silent allow-through
"""

import ast
from pathlib import Path

import services.claim_extraction
import services.claim_verification
from domain.enums import EvidenceRelationship, VerificationStatus
from domain.models import Claim
from services.claim_extraction.extractor import (
    ClaimExtractor,
    DeterministicClaimExtractor,
)
from services.claim_verification import (
    VERIFIER_VERSION,
    GeneratedTextVerifier,
    VerifiedResponse,
    build_audit_meta,
    relationship_to_status,
    unverified_failure_response,
)
from services.evidence_corpus.models import EvidenceDocument
from services.evidence_corpus.retrieval import EvidenceRetriever
from services.evidence_corpus.store import InMemoryEvidenceStore
from services.evidence_relationship.assessor import (
    DeterministicRelationshipAssessor,
    EvidenceRelationshipAssessor,
)

_FORBIDDEN_AUTHORITY_IDENTIFIERS = {
    "action",
    "decision",
    "policy_id",
    "policy_version",
    "PolicyAction",
    "PolicyDecision",
}

_CORPUS_VERSION = "unit-corpus-v1"
_DOCUMENTS = [
    EvidenceDocument(
        source_id="CCDS-TESTDRUG-V1",
        title="Company Core Data Sheet - TESTDRUG",
        text=(
            "TESTDRUG is indicated once daily with food. "
            "The maximum daily dose is 2000 mg. "
            "Dose adjustment is required in renal impairment."
        ),
        topics=["testdrug", "dose", "dosing", "renal"],
    ),
    EvidenceDocument(
        source_id="STUDY-T1-SUMMARY",
        title="Trial Summary T1",
        text="TESTDRUG showed clinically meaningful symptom relief at twelve weeks.",
        topics=["trial", "efficacy"],
    ),
]


def _corpus_store() -> InMemoryEvidenceStore:
    return InMemoryEvidenceStore(_DOCUMENTS, version=_CORPUS_VERSION)


def _verifier(
    *,
    store: InMemoryEvidenceStore | None = None,
    extractor: ClaimExtractor | None = None,
    assessor: EvidenceRelationshipAssessor | None = None,
) -> GeneratedTextVerifier:
    return GeneratedTextVerifier(
        extractor=extractor or DeterministicClaimExtractor(),
        retriever=EvidenceRetriever(store=store or _corpus_store()),
        assessor=assessor or DeterministicRelationshipAssessor(),
    )


# --- conservative mapping --------------------------------------------------------------


def test_relationship_mapping_is_conservative_per_value():
    assert relationship_to_status(EvidenceRelationship.SUPPORTS) == (VerificationStatus.SUPPORTED)
    assert relationship_to_status(EvidenceRelationship.CONTRADICTS) == (
        VerificationStatus.UNSUPPORTED
    )
    assert relationship_to_status(EvidenceRelationship.CONFLICTING) == (
        VerificationStatus.UNSUPPORTED
    )
    assert relationship_to_status(EvidenceRelationship.INSUFFICIENT) == (
        VerificationStatus.UNVERIFIABLE
    )


# --- structure: evidence and provenance only, never authority --------------------------


def _sample_responses() -> list[VerifiedResponse]:
    supported = _verifier().verify("The maximum daily dose is 2000 mg.")
    failed = unverified_failure_response("RuntimeError", error_kind="verification_failed")
    return [supported, failed]


def test_responses_never_carry_policy_authority_attributes():
    for response in _sample_responses():
        for field in VerifiedResponse.FORBIDDEN_FIELDS:
            assert not hasattr(response, field)


def test_package_modules_never_reference_policy_authority_identifiers():
    package_dirs = [
        Path(services.claim_verification.__file__).parent,
        Path(services.claim_extraction.__file__).parent,
    ]
    for package_dir in package_dirs:
        for path in sorted(package_dir.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
                node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
            }
            leaked = _FORBIDDEN_AUTHORITY_IDENTIFIERS & identifiers
            assert not leaked, f"{path.name} references policy authority: {sorted(leaked)}"


# --- end-to-end behaviour over a supplied in-memory corpus ----------------------------


def test_supported_claim_is_recorded_with_supporting_source_provenance():
    response = _verifier().verify("The maximum daily dose is 2000 mg.")

    assert response.succeeded is True
    assert response.claims_extracted == 1
    assert response.corpus_version == _CORPUS_VERSION

    (assessment,) = response.assessment.assessments
    assert assessment.status == VerificationStatus.SUPPORTED
    assert assessment.relationship == EvidenceRelationship.SUPPORTS
    assert [e.source_id for e in assessment.supporting_evidence] == ["CCDS-TESTDRUG-V1"]
    assert response.assessment.all_verified is True
    assert response.assessment.unverified_claims == []


def test_contradicted_claim_resolves_to_unsupported():
    response = _verifier().verify("TESTDRUG does not require dose adjustment.")

    (assessment,) = response.assessment.assessments
    assert assessment.status == VerificationStatus.UNSUPPORTED
    assert assessment.relationship == EvidenceRelationship.CONTRADICTS
    assert response.assessment.all_verified is False
    assert response.assessment.unverified_claims == [assessment.claim.text]


def test_unrelated_claim_resolves_to_unverifiable():
    response = _verifier().verify("Completely unrelated remark about staplers and tape.")

    (assessment,) = response.assessment.assessments
    assert assessment.status == VerificationStatus.UNVERIFIABLE
    assert assessment.relationship == EvidenceRelationship.INSUFFICIENT
    assert assessment.supporting_evidence == []


def test_disagreeing_passages_resolve_to_conflicting_then_unsupported():
    conflicting_docs = [
        EvidenceDocument(
            source_id="EFF-A",
            title="Positive note",
            text="TESTDRUG relieves cough effectively.",
            topics=["testdrug"],
        ),
        EvidenceDocument(
            source_id="EFF-B",
            title="Negative note",
            text="TESTDRUG does not relieve cough.",
            topics=["testdrug"],
        ),
    ]
    response = _verifier(store=InMemoryEvidenceStore(conflicting_docs)).verify(
        "TESTDRUG relieves cough."
    )

    (assessment,) = response.assessment.assessments
    assert assessment.relationship == EvidenceRelationship.CONFLICTING
    assert assessment.status == VerificationStatus.UNSUPPORTED
    assert assessment.supporting_evidence == []


def test_provenance_versions_are_propagated_from_components():
    response = _verifier().verify("The maximum daily dose is 2000 mg.")

    assert response.verifier_version == VERIFIER_VERSION
    assert response.corpus_version == _CORPUS_VERSION
    assert response.retrieval_version
    assert response.relationship_version


def test_empty_generation_is_a_clean_vacuous_result_not_a_finding():
    response = _verifier().verify("")

    assert response.succeeded is True
    assert response.claims_extracted == 0
    assert response.corpus_version is None
    assert response.assessment.assessments == []
    assert response.assessment.all_verified is True


def test_generation_without_extractable_claims_verifies_vacuously():
    response = _verifier().verify("..! ??")

    assert response.claims_extracted == 0
    assert response.assessment.all_verified is True


# --- fail-closed behaviour ------------------------------------------------------------


class _ExplodingExtractor(ClaimExtractor):
    """Simulates any unexpected extraction-stage outage."""

    def extract(self, generated_text: str) -> list[Claim]:
        raise RuntimeError("extraction backend down")


def test_any_internal_failure_degrades_to_an_unverified_synthetic_claim():
    response = _verifier(extractor=_ExplodingExtractor()).verify(
        "Whatever this said cannot be checked now."
    )

    assert response.succeeded is False
    assert response.error_kind == "verification_failed"
    assert response.claims_extracted == 0

    # Conservative degradation: the synthetic UNVERIFIABLE claim keeps the
    # aggregate unverified, so policy routes the response to REVIEW
    # (EVIDENCE-001) — never silently back to ALLOW.
    (assessment,) = response.assessment.assessments
    assert assessment.status == VerificationStatus.UNVERIFIABLE
    assert response.assessment.all_verified is False
    assert response.assessment.unverified_claims == [assessment.claim.text]


def test_verify_never_raises_on_unexpected_input():
    response = _verifier(extractor=_ExplodingExtractor()).verify(None)  # type: ignore[arg-type]

    assert response.succeeded is False


def test_failed_retrieval_behaves_like_an_empty_corpus_for_that_claim():
    class _BrokenStore(InMemoryEvidenceStore):
        def load(self):
            raise TimeoutError("store down")

    response = _verifier(store=_BrokenStore(_DOCUMENTS)).verify(
        "The maximum daily dose is 2000 mg."
    )

    # The STAGE succeeds; the claim simply cannot be grounded, so it degrades
    # conservatively exactly like a claim with no applicable evidence.
    assert response.succeeded is True
    (assessment,) = response.assessment.assessments
    assert assessment.status == VerificationStatus.UNVERIFIABLE
    assert assessment.supporting_evidence == []


# --- audit meta reduction --------------------------------------------------------------


def test_audit_meta_carries_the_exact_assessment_the_engine_consumed():
    verification = _verifier().verify("The maximum daily dose is 2000 mg.")

    meta = build_audit_meta(verification)

    assert meta.attempted is True
    assert meta.succeeded is True
    assert meta.applied is True
    assert meta.assessment is verification.assessment
    assert meta.corpus_version == _CORPUS_VERSION
    assert meta.failure_kind is None


def test_audit_meta_marks_failures_via_failure_kind_not_hidden_success():
    meta = build_audit_meta(unverified_failure_response("RuntimeError", error_kind="x"))

    assert meta.attempted is True
    assert meta.succeeded is False
    assert meta.applied is False
    assert meta.failure_kind == "x"
