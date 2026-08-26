"""PolicyEngine input_types matching for optical rules."""

from domain.enums import DataSensitivity, PolicyAction, RiskCategory, RiskLevel
from domain.models import RiskAssessment
from services.policy_engine.engine import PolicyEngine

engine = PolicyEngine()


def test_image_pii_hits_optical_rewrite_rule():
    risk = RiskAssessment(
        risk_level=RiskLevel.MEDIUM,
        categories=[RiskCategory.PII],
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
    )
    decision = engine.evaluate(risk, "researcher", input_type="image")
    assert decision.action == PolicyAction.REWRITE
    assert decision.policy_id == "OPT-PII-REWRITE-001"


def test_text_pii_still_hits_pii_001():
    risk = RiskAssessment(
        risk_level=RiskLevel.MEDIUM,
        categories=[RiskCategory.PII],
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
    )
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.REWRITE
    assert decision.policy_id == "PII-001"


def test_image_phi_hits_optical_review_rule():
    risk = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        categories=[RiskCategory.PHI],
        data_sensitivity=DataSensitivity.PATIENT_IDENTIFIABLE,
    )
    decision = engine.evaluate(risk, "researcher", input_type="image")
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "OPT-PHI-REVIEW-001"


def test_text_phi_still_hits_phi_001():
    risk = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        categories=[RiskCategory.PHI],
        data_sensitivity=DataSensitivity.PATIENT_IDENTIFIABLE,
    )
    decision = engine.evaluate(risk, "researcher")
    assert decision.action == PolicyAction.REVIEW
    assert decision.policy_id == "PHI-001"


def test_image_with_pii_and_phi_prefers_rewrite_first():
    """OPT-PII-REWRITE is ordered before OPT-PHI-REVIEW → sanitizable path."""
    risk = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        categories=[RiskCategory.PHI, RiskCategory.PII],
        data_sensitivity=DataSensitivity.PATIENT_IDENTIFIABLE,
    )
    decision = engine.evaluate(risk, "researcher", input_type="image")
    assert decision.action == PolicyAction.REWRITE
    assert decision.policy_id == "OPT-PII-REWRITE-001"
