"""Normalize OpticalAssessment → RiskAssessment (non-authoritative).

Mirrors sensitivity precedence from the text keyword classifier. Never sets
a policy action — PolicyEngine is the sole authority.
Integrates multimodal threat categories from unified classifier.
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
    RiskCategory.CYBER_SAFETY: DataSensitivity.INTERNAL,
    RiskCategory.AUTHORITY_SPOOFING: DataSensitivity.INTERNAL,
    RiskCategory.DATA_EXFILTRATION: DataSensitivity.PATIENT_IDENTIFIABLE,
    RiskCategory.PHISHING: DataSensitivity.CONFIDENTIAL,
    RiskCategory.MALWARE: DataSensitivity.INTERNAL,
    RiskCategory.MULTIMODAL_UNTRUSTED: DataSensitivity.INTERNAL,
}


def _sensitivity_for(categories: list[RiskCategory]) -> DataSensitivity:
    chosen = DataSensitivity.INTERNAL
    for category in categories:
        candidate = _CATEGORY_SENSITIVITY.get(category, DataSensitivity.INTERNAL)
        if _SENSITIVITY_RANK[candidate] > _SENSITIVITY_RANK[chosen]:
            chosen = candidate
    return chosen


def normalize_optical_assessment(assessment: OpticalAssessment) -> RiskAssessment:
    """Convert optical + multimodal evidence into RiskAssessment."""
    categories: list[RiskCategory] = []
    injection = assessment.injection_detected or any(
        f.category == RiskCategory.PROMPT_INJECTION for f in assessment.findings
    )

    has_pii = any(f.category == RiskCategory.PII for f in assessment.findings)
    has_phi = any(f.category == RiskCategory.PHI for f in assessment.findings)
    has_exfil = assessment.data_exfiltration or any(
        f.category == RiskCategory.DATA_EXFILTRATION for f in assessment.findings
    )
    has_authority = assessment.authority_spoofing or any(
        f.category == RiskCategory.AUTHORITY_SPOOFING for f in assessment.findings
    )
    has_malware = any(f.category == RiskCategory.MALWARE for f in assessment.findings)
    has_phishing = any(f.category == RiskCategory.PHISHING for f in assessment.findings)
    has_cyber = any(f.category == RiskCategory.CYBER_SAFETY for f in assessment.findings)
    has_multimodal = any(
        f.category == RiskCategory.MULTIMODAL_UNTRUSTED for f in assessment.findings
    )

    has_manufacturing = "MANUFACTURING_SAFETY_VIOLATION" in (assessment.multimodal_categories or [])
    has_regulatory = "REGULATORY_MANIPULATION_ATTEMPT" in (assessment.multimodal_categories or [])

    if injection:
        categories.append(RiskCategory.PROMPT_INJECTION)
    if has_exfil:
        categories.append(RiskCategory.DATA_EXFILTRATION)
    if has_authority:
        categories.append(RiskCategory.AUTHORITY_SPOOFING)
    if has_malware:
        categories.append(RiskCategory.MALWARE)
    if has_phishing:
        categories.append(RiskCategory.PHISHING)
    if has_cyber:
        categories.append(RiskCategory.CYBER_SAFETY)
    if has_multimodal:
        categories.append(RiskCategory.MULTIMODAL_UNTRUSTED)
    if has_phi:
        categories.append(RiskCategory.PHI)
    if has_pii:
        categories.append(RiskCategory.PII)

    if injection or has_exfil or has_malware or has_manufacturing or has_regulatory:
        level = RiskLevel.CRITICAL
    elif has_authority or has_phishing or assessment.qr_detected:
        level = RiskLevel.HIGH
    elif has_phi or has_multimodal or has_cyber:
        level = RiskLevel.HIGH if has_phi else RiskLevel.MEDIUM
    elif has_pii:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    if not categories:
        categories = [RiskCategory.NONE]

    finding_types = sorted({f.type for f in assessment.findings})
    mm_cats = assessment.multimodal_categories or []
    reasoning = (
        f"Optical+multimodal normalizer: document_type={assessment.document_type!r}, "
        f"findings={finding_types or ['NONE']}, multimodal={mm_cats or ['NONE']}"
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
