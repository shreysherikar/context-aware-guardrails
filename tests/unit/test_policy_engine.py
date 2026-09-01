from pathlib import Path

import pytest

from domain.enums import (
    DataSensitivity,
    EvidenceRelationship,
    PolicyAction,
    RiskCategory,
    RiskLevel,
    VerificationStatus,
)
from domain.models import (
    Claim,
    ClaimEvidenceAssessment,
    EvidenceAssessment,
    RiskAssessment,
    TrajectoryAssessment,
)
from services.policy_engine.engine import PolicyEngine
from services.policy_engine.policy_models import PolicyValidationError

engine = PolicyEngine()


def test_allow_low_risk():
    risk = RiskAssessment(risk_level=RiskLevel.LOW, categories=[RiskCategory.NONE])
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.ALLOW


def test_block_on_disguise_regardless_of_category():
    risk = RiskAssessment(
        risk_level=RiskLevel.CRITICAL,
        categories=[RiskCategory.PROMPT_INJECTION],
        disguise_detected=True,
    )
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.BLOCK
    assert decision.policy_id == "INJECTION-001"


def test_block_on_injection_alone():
    """injection_detected without disguise_detected must still be BLOCKed."""
    risk = RiskAssessment(
        risk_level=RiskLevel.CRITICAL,
        categories=[RiskCategory.PROMPT_INJECTION],
        disguise_detected=False,
        injection_detected=True,
    )
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.BLOCK
    assert decision.policy_id == "INJECTION-002"


def test_block_on_disguise_alone():
    risk = RiskAssessment(
        risk_level=RiskLevel.CRITICAL,
        categories=[RiskCategory.PROMPT_INJECTION],
        disguise_detected=True,
        injection_detected=False,
    )
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.BLOCK
    assert decision.policy_id == "INJECTION-001"


def test_review_on_patient_identifiable_phi():
    risk = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        categories=[RiskCategory.PHI],
        data_sensitivity=DataSensitivity.PATIENT_IDENTIFIABLE,
    )
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.REVIEW


def test_rewrite_on_pii():
    """PII without PHI routes to REWRITE (the pre-existing PII-001 rule)."""
    risk = RiskAssessment(
        risk_level=RiskLevel.MEDIUM,
        categories=[RiskCategory.PII],
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
    )
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.REWRITE
    assert decision.policy_id == "PII-001"


def test_fails_closed_when_no_rule_matches():
    """A risk profile no rule anticipates must never default to ALLOW."""
    risk = RiskAssessment(risk_level=RiskLevel.MEDIUM, categories=[RiskCategory.NONE])
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "DEFAULT-FAIL-CLOSED"


def test_invalid_policy_configuration_fails_at_load(tmp_path):
    """A broken policy must raise loudly at load time, not mid-request."""
    bad_policy = tmp_path / "broken.yaml"
    bad_policy.write_text("version: '0.1.0'\nrules:\n  - id: BAD\n    action: NOT_A_REAL_ACTION\n")
    with pytest.raises(PolicyValidationError):
        PolicyEngine(policy_path=bad_policy)


def test_missing_policy_file_fails_at_load(tmp_path):
    with pytest.raises(PolicyValidationError):
        PolicyEngine(policy_path=tmp_path / "does_not_exist.yaml")


def test_policy_path_reads_from_environment(tmp_path, monkeypatch):
    custom = tmp_path / "custom.yaml"
    custom.write_text("version: '1'\nrules: []\n")
    monkeypatch.setenv("POLICY_PATH", str(custom))
    eng = PolicyEngine()
    assert eng.policy_path == custom


def test_policy_path_default_is_repo_default(monkeypatch):
    monkeypatch.delenv("POLICY_PATH", raising=False)
    eng = PolicyEngine()
    assert eng.policy_path == Path(__file__).resolve().parents[2] / "policies" / "policy.yaml"


def test_first_matching_rule_wins(tmp_path):
    """Rules are evaluated top to bottom and the first match decides.

    With only the FIRST-ALLOW rule (risk_level LOW) present, a LOW profile is
    allowed; with the CATCH-ALL-BLOCK rule appended, the same profile must be
    blocked because LOW-001 no longer exists and the catch-all is the first
    match. This proves order (not content) decides which rule applies.
    """
    ordered = tmp_path / "ordered.yaml"
    ordered.write_text(
        "version: '1'\n"
        "rules:\n"
        "  - id: FIRST-ALLOW\n"
        "    description: 'first rule allows LOW'\n"
        "    risk_level: LOW\n"
        "    action: ALLOW\n"
    )
    first = PolicyEngine(policy_path=ordered)
    risk = RiskAssessment(risk_level=RiskLevel.LOW, categories=[RiskCategory.NONE])
    assert first.evaluate(risk, "researcher").policy_id == "FIRST-ALLOW"

    ordered.write_text(
        "version: '1'\n"
        "rules:\n"
        "  - id: FIRST-ALLOW\n"
        "    description: 'first rule allows LOW'\n"
        "    risk_level: LOW\n"
        "    action: ALLOW\n"
        "  - id: CATCH-ALL-BLOCK\n"
        "    description: 'second rule blocks everything'\n"
        "    action: BLOCK\n"
    )
    second = PolicyEngine(policy_path=ordered)
    assert second.evaluate(risk, "researcher").policy_id == "FIRST-ALLOW"


def test_precedence_most_specific_rule_wins(tmp_path):
    """When two rules both match, the FIRST listed one decides.

    LOW-001 is deliberately ordered before a CATCH-ALL-BLOCK in the policy
    file; a LOW profile matches both, and the engine must return LOW-001, not
    the later catch-all. Reversing the file order must reverse the outcome.
    """
    ordered = tmp_path / "ordered.yaml"
    ordered.write_text(
        "version: '1'\n"
        "rules:\n"
        "  - id: LOW-001\n"
        "    description: 'LOW allowed'\n"
        "    risk_level: LOW\n"
        "    action: ALLOW\n"
        "  - id: CATCH-ALL-BLOCK\n"
        "    description: 'blocks everything else'\n"
        "    action: BLOCK\n"
    )
    risk = RiskAssessment(risk_level=RiskLevel.LOW, categories=[RiskCategory.NONE])

    engine_a = PolicyEngine(policy_path=ordered)
    assert engine_a.evaluate(risk, "researcher").policy_id == "LOW-001"

    reversed_yaml = tmp_path / "reversed.yaml"
    reversed_yaml.write_text(
        "version: '1'\n"
        "rules:\n"
        "  - id: CATCH-ALL-BLOCK\n"
        "    description: 'blocks everything'\n"
        "    action: BLOCK\n"
        "  - id: LOW-001\n"
        "    description: 'LOW allowed'\n"
        "    risk_level: LOW\n"
        "    action: ALLOW\n"
    )
    engine_b = PolicyEngine(policy_path=reversed_yaml)
    assert engine_b.evaluate(risk, "researcher").policy_id == "CATCH-ALL-BLOCK"


# --- trajectory condition -----------------------------------------------------


def _trajectory_risk() -> RiskAssessment:
    """An individually-ALLOW-able risk profile (LOW / NONE)."""
    return RiskAssessment(risk_level=RiskLevel.LOW, categories=[RiskCategory.NONE])


def test_trajectory_escalation_routes_low_turn_to_review():
    risk = _trajectory_risk()
    trajectory = TrajectoryAssessment(escalate=True, reason="repeated PII probe")
    decision = engine.evaluate(risk, "researcher", trajectory=trajectory)
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "TRAJECTORY-001"


def test_no_escalation_keeps_single_turn_behavior():
    risk = _trajectory_risk()
    trajectory = TrajectoryAssessment(escalate=False, reason="no pattern")
    decision = engine.evaluate(risk, "researcher", trajectory=trajectory)
    assert decision.action == PolicyAction.ALLOW
    assert decision.policy_id == "LOW-001"


def test_missing_trajectory_skips_trajectory_rule():
    """Existing single-turn callers (no trajectory) must be unaffected."""
    risk = _trajectory_risk()
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.ALLOW
    assert decision.policy_id == "LOW-001"


def test_direct_block_rules_take_priority_over_escalation():
    """A direct-match BLOCK rule on this turn wins regardless of history."""
    risk = RiskAssessment(
        risk_level=RiskLevel.CRITICAL,
        categories=[RiskCategory.PROMPT_INJECTION],
        injection_detected=True,
    )
    trajectory = TrajectoryAssessment(escalate=True, reason="prior probing")
    decision = engine.evaluate(risk, "researcher", trajectory=trajectory)
    assert decision.action == PolicyAction.BLOCK
    assert decision.policy_id == "INJECTION-002"


def test_direct_review_rules_take_priority_over_escalation():
    """PHI-001 (direct REVIEW) still matches first even when escalation is set."""
    risk = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        categories=[RiskCategory.PHI],
        data_sensitivity=DataSensitivity.PATIENT_IDENTIFIABLE,
    )
    trajectory = TrajectoryAssessment(escalate=True, reason="prior probing")
    decision = engine.evaluate(risk, "researcher", trajectory=trajectory)
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "PHI-001"


# --- claim/evidence verification conditions ------------------------------------


def _claim(text: str) -> Claim:
    return Claim(text=text, confidence=0.9)


def _claim_assessment(
    text: str,
    *,
    status: VerificationStatus,
    relationship: EvidenceRelationship | None = None,
) -> EvidenceAssessment:
    """One per-claim verdict as a verification stage emits it: ``status`` is
    mandatory; ``relationship`` only when the corpus assessor ran."""
    return EvidenceAssessment(
        claim=_claim(text),
        status=status,
        relationship=relationship,
        reasoning="checked against approved sources",
        confidence=0.8,
    )


def _supported_claim(text: str) -> EvidenceAssessment:
    return _claim_assessment(
        text,
        status=VerificationStatus.SUPPORTED,
        relationship=EvidenceRelationship.SUPPORTS,
    )


def _contradicted_claim(text: str) -> EvidenceAssessment:
    return _claim_assessment(
        text,
        status=VerificationStatus.UNSUPPORTED,
        relationship=EvidenceRelationship.CONTRADICTS,
    )


def _claims(*assessments: EvidenceAssessment) -> ClaimEvidenceAssessment:
    return ClaimEvidenceAssessment(assessments=list(assessments))


def test_high_risk_with_insufficient_evidence_routes_to_review():
    """HIGH-risk turn plus an INSUFFICIENT verdict lands on EVIDENCE-001 REVIEW.

    This exact profile would otherwise fall through to the fail-closed default
    BLOCK, so matching EVIDENCE-001 proves the new rule decided — deterministically
    from the risk profile plus the supplied evidence alone.
    """
    risk = RiskAssessment(risk_level=RiskLevel.HIGH, categories=[RiskCategory.NONE])
    claims = _claims(
        _claim_assessment(
            "Drug X cures condition Y",
            status=VerificationStatus.UNVERIFIABLE,
            relationship=EvidenceRelationship.INSUFFICIENT,
        )
    )
    decision = engine.evaluate(risk, "researcher", claims=claims)
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "EVIDENCE-001"


def test_contradicted_claim_routes_to_review():
    """One CONTRADICTS verdict makes the whole assessment unverified, even
    alongside a fully supported claim."""
    risk = RiskAssessment(risk_level=RiskLevel.MEDIUM, categories=[RiskCategory.NONE])
    claims = _claims(
        _contradicted_claim("Drug X cures condition Y"),
        _supported_claim("Drug X treats condition Y"),
    )
    decision = engine.evaluate(risk, "researcher", claims=claims)
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "EVIDENCE-001"


def test_conflicting_evidence_routes_to_review():
    """CONFLICTING passages cannot be resolved automatically — human review."""
    risk = RiskAssessment(risk_level=RiskLevel.MEDIUM, categories=[RiskCategory.NONE])
    claims = _claims(
        _claim_assessment(
            "Drug X cures condition Y",
            status=VerificationStatus.UNSUPPORTED,
            relationship=EvidenceRelationship.CONFLICTING,
        ),
    )
    decision = engine.evaluate(risk, "researcher", claims=claims)
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "EVIDENCE-001"


def test_supported_claim_does_not_trigger_evidence_review():
    """A fully supported claim clears EVIDENCE-001 and falls through unchanged."""
    risk = RiskAssessment(risk_level=RiskLevel.LOW, categories=[RiskCategory.NONE])
    claims = _claims(_supported_claim("Drug X treats condition Y"))
    decision = engine.evaluate(risk, "researcher", claims=claims)
    assert decision.action == PolicyAction.ALLOW
    assert decision.policy_id == "LOW-001"


def test_low_risk_with_unsupported_claims_routes_to_evidence_review():
    """LOW-risk turns with unsupported claims trigger EVIDENCE-001 because
    evidence verification is a post-generation output-side check, not gated by
    the input's risk level. A low-risk input can still produce hallucinations."""
    risk = RiskAssessment(risk_level=RiskLevel.LOW, categories=[RiskCategory.NONE])
    claims = _claims(_contradicted_claim("Drug X cures condition Y"))
    decision = engine.evaluate(risk, "researcher", claims=claims)
    # Unsupported claims always escalate to EVIDENCE-001 REVIEW, regardless of
    # input risk level, because the risk lives in the generated output.
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "EVIDENCE-001"


def test_missing_claim_assessment_skips_evidence_rule():
    """Backward compatibility: callers without a verification stage unaffected."""
    risk = RiskAssessment(risk_level=RiskLevel.LOW, categories=[RiskCategory.NONE])
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.ALLOW
    assert decision.policy_id == "LOW-001"


def test_disagreeing_metadata_resolves_conservatively_not_as_verified():
    """A SUPPORTED status next to a CONTRADICTS relationship can never certify
    the claim: the aggregate reads its weakest metadata (fail closed)."""
    risk = RiskAssessment(risk_level=RiskLevel.MEDIUM, categories=[RiskCategory.NONE])
    claims = _claims(
        _claim_assessment(
            "Drug X cures condition Y",
            status=VerificationStatus.SUPPORTED,
            relationship=EvidenceRelationship.CONTRADICTS,
        ),
    )
    decision = engine.evaluate(risk, "researcher", claims=claims)
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "EVIDENCE-001"


def test_direct_block_rules_take_priority_over_evidence_review():
    """An input-plane injection block still wins over output-evidence review."""
    risk = RiskAssessment(
        risk_level=RiskLevel.CRITICAL,
        categories=[RiskCategory.PROMPT_INJECTION],
        injection_detected=True,
    )
    decision = engine.evaluate(
        risk,
        "researcher",
        claims=_claims(_contradicted_claim("Drug X cures condition Y")),
    )
    assert decision.action == PolicyAction.BLOCK
    assert decision.policy_id == "INJECTION-002"


def test_trajectory_review_takes_priority_over_evidence_review():
    """TRAJECTORY-001 sits above EVIDENCE-001: conversation history first."""
    risk = RiskAssessment(risk_level=RiskLevel.MEDIUM, categories=[RiskCategory.NONE])
    trajectory = TrajectoryAssessment(escalate=True, reason="prior probing")
    decision = engine.evaluate(
        risk,
        "researcher",
        trajectory=trajectory,
        claims=_claims(_contradicted_claim("Drug X cures condition Y")),
    )
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "TRAJECTORY-001"


@pytest.mark.parametrize(
    ("risk", "baseline_policy_id"),
    [
        (
            RiskAssessment(
                risk_level=RiskLevel.MEDIUM,
                categories=[RiskCategory.PII],
                data_sensitivity=DataSensitivity.CONFIDENTIAL,
            ),
            "PII-001",
        ),
        (
            RiskAssessment(risk_level=RiskLevel.MEDIUM, categories=[RiskCategory.OFF_LABEL]),
            "OFFLABEL-001",
        ),
    ],
)
def test_evidence_review_outranks_single_turn_friction_rules(risk, baseline_policy_id):
    """Without an assessment the friction rule (REWRITE/CLARIFY) fires; with one
    whose claims are unsupported, EVIDENCE-001 must take precedence instead —
    rewriting or clarifying cannot repair an unsupported generated claim."""
    baseline = engine.evaluate(risk, "researcher")
    assert baseline.policy_id == baseline_policy_id

    with_claims = engine.evaluate(
        risk, "researcher", claims=_claims(_contradicted_claim("Drug X cures condition Y"))
    )
    assert with_claims.action == PolicyAction.REVIEW
    assert with_claims.policy_id == "EVIDENCE-001"
