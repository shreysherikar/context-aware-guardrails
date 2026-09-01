"""Pharma-domain risk patterns (ambiguous prompt dataset + guardrail brief)."""

from __future__ import annotations

import re

from domain.enums import RiskCategory

PHARMA_RISK_PATTERNS: list[tuple[str, RiskCategory, str]] = [
    (
        r"increase prescription",
        RiskCategory.OFF_LABEL,
        "Promotional outcome ('increase prescriptions') without approved indication or fair balance.",
    ),
    (
        r"which hcps? to priorit",
        RiskCategory.OFF_LABEL,
        "Ambiguous HCP targeting without selection criteria or governance constraints.",
    ),
    (
        r"prioritiz\w+.*\bhcp",
        RiskCategory.OFF_LABEL,
        "HCP prioritization request lacks data-source and policy constraints.",
    ),
    (
        r"patient specifics",
        RiskCategory.PHI,
        "'Patient specifics' may pull PHI into customer-facing outreach content.",
    ),
    (
        r"likelihood to start therapy",
        RiskCategory.PHI,
        "Patient-level therapy likelihood inference may violate privacy and targeting rules.",
    ),
    (
        r"social media comments.*patient",
        RiskCategory.PHI,
        "Social-derived patient insights raise consent and data-provenance concerns.",
    ),
    (
        r"counter[- ]arguments.*(competitor|win the)",
        RiskCategory.OFF_LABEL,
        "Competitive counter-arguments may produce non-fair-balanced promotional claims.",
    ),
    (
        r"reps should receive incentives",
        RiskCategory.OFF_LABEL,
        "Incentive recommendations require documented compliance controls.",
    ),
    (
        r"stronger and more convincing.*evidence is limited|even if evidence is limited",
        RiskCategory.PROMPT_INJECTION,
        "Disguised request to strengthen claims despite limited evidence.",
    ),
    (
        r"what the patient might be experiencing",
        RiskCategory.PHI,
        "Speculative patient medical statements risk unverified clinical content.",
    ),
    (
        r"draft a follow-up email after the call using",
        RiskCategory.PHI,
        "Call-note follow-ups may leak PHI unless explicitly de-identified.",
    ),
    (
        r"targeting list",
        RiskCategory.OFF_LABEL,
        "Targeting list creation without consent or segmentation rules is ambiguous.",
    ),
    (
        r"personalized campaigns",
        RiskCategory.PHI,
        "Personalized campaigns may imply individualized outreach without consent.",
    ),
]

SAFE_PHARMA_SIGNALS: list[str] = [
    r"do not include individual hcp identifiers",
    r"approved materials",
    r"fair[- ]balance",
    r"aggregat",
    r"non[- ]identifying",
    r"compliance checklist",
    r"stated as hypotheses only",
    r"without adding medical interpretations",
    r"if evidence is missing",
]


def match_pharma_patterns(text: str) -> list[tuple[RiskCategory, str]]:
    lower = text.lower()
    hits: list[tuple[RiskCategory, str]] = []
    seen: set[RiskCategory] = set()
    for pattern, category, reason in PHARMA_RISK_PATTERNS:
        if re.search(pattern, lower) and category not in seen:
            hits.append((category, reason))
            seen.add(category)
    return hits


def has_safe_pharma_signals(text: str) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in SAFE_PHARMA_SIGNALS)
