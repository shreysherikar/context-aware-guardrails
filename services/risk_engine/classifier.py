"""
Risk classification (reasoning plane — probabilistic).

RiskClassifier is the abstract contract. KeywordMockClassifier is a
deliberately simple, dependency-free, fully deterministic implementation used
to exercise the pipeline without any real model call.

To move to a real LLM, write a new class implementing
`classify(request) -> RiskAssessment` with the same signature — nothing else
in the system needs to change, because policy_engine and audit only ever see
a RiskAssessment, never the model that produced it.
"""

import re

from domain.enums import DataSensitivity, RiskCategory, RiskLevel
from domain.models import GuardrailRequest, RiskAssessment

# Sensitivity precedence: a more sensitive classification must never be
# downgraded. When several categories match, the highest sensitivity wins —
# PHI (patient-identifiable data) always outranks PII, never the reverse.
_SENSITIVITY_RANK = {
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.INTERNAL: 1,
    DataSensitivity.CONFIDENTIAL: 2,
    DataSensitivity.PATIENT_IDENTIFIABLE: 3,
}

_CATEGORY_SENSITIVITY = {
    RiskCategory.PHI: DataSensitivity.PATIENT_IDENTIFIABLE,
    RiskCategory.PII: DataSensitivity.CONFIDENTIAL,
    # OFF_LABEL, IP and PROMPT_INJECTION intentionally keep the INTERNAL
    # default, matching the pre-existing behaviour of the keyword classifier.
    RiskCategory.OFF_LABEL: DataSensitivity.INTERNAL,
    RiskCategory.IP: DataSensitivity.INTERNAL,
    RiskCategory.PROMPT_INJECTION: DataSensitivity.INTERNAL,
}


def _sensitivity_for(categories: list[RiskCategory]) -> DataSensitivity:
    """Return the highest-sensitivity classification among the matched categories."""
    chosen = DataSensitivity.INTERNAL
    for category in categories:
        candidate = _CATEGORY_SENSITIVITY.get(category, DataSensitivity.INTERNAL)
        if _SENSITIVITY_RANK[candidate] > _SENSITIVITY_RANK[chosen]:
            chosen = candidate
    return chosen


class RiskClassifier:
    def classify(self, request: GuardrailRequest) -> RiskAssessment:
        raise NotImplementedError


class KeywordMockClassifier(RiskClassifier):
    INJECTION_PATTERNS = [
        r"ignore (all |any |previous |prior )?instructions",
        r"pretend you('re| are) (an? )?unrestricted",
        r"no policy limits",
        r"disregard (your |the )?(rules|guidelines|policy)",
        r"note to the (risk )?classifier",
        r"score this as low risk",
    ]
    PHI_PATTERNS = [
        r"patient name",
        r"adverse reaction",
        r"medical record number",
        r"patient[- ]level",
        r"identifiable patient",
    ]
    PII_PATTERNS = [r"\bssn\b", r"social security", r"date of birth", r"home address"]
    OFF_LABEL_PATTERNS = [r"off[- ]label", r"unapproved use", r"efficacy claim"]
    IP_PATTERNS = [r"proprietary formula", r"trade secret", r"unreleased pipeline data"]

    def classify(self, request: GuardrailRequest) -> RiskAssessment:
        text = request.prompt.lower()

        injection = any(re.search(p, text) for p in self.INJECTION_PATTERNS)
        categories: list[RiskCategory] = []

        if any(re.search(p, text) for p in self.PHI_PATTERNS):
            categories.append(RiskCategory.PHI)
        if any(re.search(p, text) for p in self.PII_PATTERNS):
            categories.append(RiskCategory.PII)
        if any(re.search(p, text) for p in self.OFF_LABEL_PATTERNS):
            categories.append(RiskCategory.OFF_LABEL)
        if any(re.search(p, text) for p in self.IP_PATTERNS):
            categories.append(RiskCategory.IP)
        if injection:
            categories.append(RiskCategory.PROMPT_INJECTION)

        if injection:
            level = RiskLevel.CRITICAL
        elif RiskCategory.PHI in categories:
            level = RiskLevel.HIGH
        elif categories:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        return RiskAssessment(
            risk_level=level,
            categories=categories or [RiskCategory.NONE],
            disguise_detected=injection,
            injection_detected=injection,
            data_sensitivity=_sensitivity_for(categories),
            confidence=0.6,
            reasoning=(
                f"Keyword mock classifier matched: {[c.value for c in categories] or ['NONE']}"
            ),
        )
