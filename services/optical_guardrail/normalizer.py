"""Normalize OpticalAssessment → RiskAssessment (non-authoritative).

Mirrors sensitivity precedence from the text keyword classifier. Never sets
a policy action — PolicyEngine is the sole authority.
"""

from __future__ import annotations

from domain.enums import DataSensitivity, RiskCategory, RiskLevel
from domain.models import OpticalAssessment, RiskAssessment

_SENSITIVITY_RANK = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.CONFIDENTIAL: 2,
    DataSensitivity.PATIENT_IDENTIFIABLE: 3,
}

_CATEGORY_SENSITIVITY = {
    RiskCategory.PHI: DataSensitivity.PATIENT_IDENTIFIABLE,
    RiskCategory.PII: DataSensitivity.CONFIDENTIAL,
    RiskCategory.OFF_LABEL: DataSensitivity.INTERNAL,
    RiskCategory.IP: DataSensitivity.INTERNAL,
    RiskCategory.PROMPT_INJECTION: DataSensitivity.INTERNAL,
}


def _sensitivity_for(categories: list[RiskCategory]) -> DataSensitivity:
    chosen = DataSensitivity.INTERNAL
    for category in categories:
        candidate = _CATEGORY_SENSITIVITY.get(category, DataSensitivity.INTERNAL)
        if _SENSITIVITY_RANK[candidate] > _SENSITIVITY_RANK[chosen]:
            chosen = candidate
    return chosen


def normalize_optical_assessment(assessment: OpticalAssessment) -> RiskAssessment:
    """Convert optical evidence into the shared RiskAssessment contract.

    Mapping (P0):
    - Injection → CRITICAL + PROMPT_INJECTION + injection/disguise flags
    - Identifier / PII findings without clinical PHI → PII / MEDIUM
    - Clinical PHI findings → PHI / HIGH / PATIENT_IDENTIFIABLE
    - Both PII and PHI → keep both categories (policy first-match decides)
    - None → LOW / NONE
    """
    categories: list[RiskCategory] = []
    injection = assessment.injection_detected or any(
        f.category == RiskCategory.PROMPT_INJECTION for f in assessment.findings
    )

    has_pii = any(f.category == RiskCategory.PII for f in assessment.findings)
    has_phi = any(f.category == RiskCategory.PHI for f in assessment.findings)

    if injection:
        categories.append(RiskCategory.PROMPT_INJECTION)
    if has_phi:
        categories.append(RiskCategory.PHI)
    if has_pii:
        categories.append(RiskCategory.PII)

    if injection:
        level = RiskLevel.CRITICAL
    elif has_phi:
        level = RiskLevel.HIGH
    elif has_pii:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    if not categories:
        categories = [RiskCategory.NONE]

    finding_types = sorted({f.type for f in assessment.findings})
    reasoning = (
        f"Optical normalizer: document_type={assessment.document_type!r}, "
        f"findings={finding_types or ['NONE']}"
    )

    return RiskAssessment(
        risk_level=level,
        categories=categories,
        disguise_detected=injection,
        injection_detected=injection,
        data_sensitivity=_sensitivity_for([c for c in categories if c != RiskCategory.NONE]),
        confidence=assessment.confidence,
        reasoning=reasoning,
    )
