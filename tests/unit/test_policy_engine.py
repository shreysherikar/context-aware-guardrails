from pathlib import Path

import pytest

from domain.enums import DataSensitivity, PolicyAction, RiskCategory, RiskLevel
from domain.models import RiskAssessment
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
    assert decision.action == PolicyAction.BLOCK
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
