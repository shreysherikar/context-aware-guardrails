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
from services.cyber_safety.darkweb import assess_darkweb_content
from services.risk_engine.pharma_patterns import has_safe_pharma_signals, match_pharma_patterns

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
    RiskCategory.CYBER_SAFETY: DataSensitivity.INTERNAL,
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
        r"stronger and more convincing.*evidence is limited",
        r"even if evidence is limited",
    ]
    PHI_PATTERNS = [
        r"patient name",
        r"adverse reaction",
        r"medical record number",
        r"patient[- ]level",
        r"identifiable patient",
        r"patient specifics",
        r"what the patient might be experiencing",
        r"likelihood to start therapy",
    ]
    PII_PATTERNS = [r"\bssn\b", r"social security", r"date of birth", r"home address"]
    OFF_LABEL_PATTERNS = [
        r"off[- ]label",
        r"unapproved use",
        r"efficacy claim",
        r"increase prescription",
        r"which hcps? to priorit",
        r"prioritiz\w+.*\bhcp",
        r"counter[- ]arguments",
        r"reps should receive incentives",
        r"targeting list",
    ]
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

        # Pharma-domain ambiguous / disguised-risk patterns (dataset + project brief).
        pharma_hits = match_pharma_patterns(request.prompt)
        pharma_reasons: list[str] = []
        for category, reason in pharma_hits:
            if category not in categories:
                categories.append(category)
            pharma_reasons.append(reason)

        # Dark-web / cyber-safety (DARKWEB_ACCESS_PREVENTION)
        darkweb = assess_darkweb_content(request.prompt, is_output=False)
        darkweb_level: RiskLevel | None = None
        if darkweb.decision != "ALLOW":
            if RiskCategory.CYBER_SAFETY not in categories:
                categories.append(RiskCategory.CYBER_SAFETY)
            pharma_reasons.extend(darkweb.reasons)
            darkweb_level = darkweb.risk_level
            if darkweb.injection_attempt:
                injection = True
                if RiskCategory.PROMPT_INJECTION not in categories:
                    categories.append(RiskCategory.PROMPT_INJECTION)

        # Well-scoped safe prompts from the dataset reduce false positives.
        if has_safe_pharma_signals(text) and not injection:
            categories = [c for c in categories if c not in (RiskCategory.OFF_LABEL,)]

        if injection:
            level = RiskLevel.CRITICAL
        elif darkweb_level == RiskLevel.CRITICAL:
            level = RiskLevel.CRITICAL
        elif darkweb_level == RiskLevel.HIGH:
            level = RiskLevel.HIGH
        elif RiskCategory.PHI in categories:
            level = RiskLevel.HIGH
        elif darkweb_level == RiskLevel.MEDIUM or categories:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        reasoning_parts = (
            pharma_reasons
            or [f"Keyword mock classifier matched: {[c.value for c in categories] or ['NONE']}"]
        )

        return RiskAssessment(
            risk_level=level,
            categories=categories or [RiskCategory.NONE],
            disguise_detected=injection or any(
                "disguised" in r.lower() or "limited evidence" in r.lower() for r in pharma_reasons
            ),
            injection_detected=injection,
            data_sensitivity=_sensitivity_for(categories),
            confidence=0.75 if pharma_reasons else 0.6,
            reasoning="; ".join(reasoning_parts),
        )
