"""Pharma agent guidance: rewrites, clarifications, and prompt classification."""

from __future__ import annotations

import re
from dataclasses import dataclass

from domain.enums import RiskLevel

from services.risk_engine.pharma_patterns import match_pharma_patterns


@dataclass(frozen=True)
class PharmaGuidance:
    clarification_questions: list[str]
    suggested_rewrite: str | None


_PHARMA_GUIDANCE: list[tuple[str, PharmaGuidance]] = [
    (
        r"increase prescription",
        PharmaGuidance(
            clarification_questions=[
                "Which approved indication and jurisdiction should this message cover?",
                "Should the draft include required fair-balance and safety language?",
            ],
            suggested_rewrite=(
                "Draft a compliant HCP follow-up using only approved claims for [Drug X] "
                "in [indication], including fair-balance phrasing from provided materials."
            ),
        ),
    ),
    (
        r"which hcps? to priorit|prioritiz\w+.*\bhcp",
        PharmaGuidance(
            clarification_questions=[
                "What selection criteria are approved (specialty, geography, engagement tier)?",
                "Should output exclude individual identifiers and use aggregate CRM data only?",
            ],
            suggested_rewrite=(
                "Using aggregate CRM data only, summarize engagement performance by region "
                "and channel. Do not include individual HCP identifiers."
            ),
        ),
    ),
    (
        r"patient specifics|draft a follow-up email after the call",
        PharmaGuidance(
            clarification_questions=[
                "Can you confirm no patient names, MRNs, or clinical details will be included?",
            ],
            suggested_rewrite=(
                "Draft a neutral follow-up email template after a call: agenda recap and "
                "request for next meeting time, using only non-identifying details."
            ),
        ),
    ),
    (
        r"off[- ]label",
        PharmaGuidance(
            clarification_questions=[
                "Is this for an approved medical-information workflow or promotional use?",
                "Which jurisdiction and evidence sources are in scope?",
            ],
            suggested_rewrite=(
                "From approved materials only, summarize on-label information for [Drug X]. "
                "If off-label context is required, label it as requiring medical affairs review."
            ),
        ),
    ),
    (
        r"stronger and more convincing|even if evidence is limited",
        PharmaGuidance(
            clarification_questions=[
                "Which approved evidence text should the slide be based on?",
            ],
            suggested_rewrite=(
                "Using only provided approved evidence, draft a slide that accurately reflects "
                "study limitations and required qualifiers. Do not strengthen claims beyond evidence."
            ),
        ),
    ),
    (
        r"likelihood to start therapy|targeting list|personalized campaigns",
        PharmaGuidance(
            clarification_questions=[
                "Can segmentation use only consented, non-sensitive attributes (e.g., specialty, geography)?",
            ],
            suggested_rewrite=(
                "Propose segmentation rules based on non-sensitive, consented attributes "
                "(specialty, geography) and clearly state assumptions. No patient-level inference."
            ),
        ),
    ),
]


def pharma_guidance_for(text: str) -> PharmaGuidance | None:
    lower = text.lower()
    for pattern, guidance in _PHARMA_GUIDANCE:
        if re.search(pattern, lower):
            return guidance
    return None


def pharma_ambiguity_notes(text: str) -> list[str]:
    """Explain why a pharma prompt is ambiguous (from dataset rationale)."""
    return [reason for _, reason in match_pharma_patterns(text)]


def prompt_class_label(action: str, risk_level: RiskLevel) -> str:
    if action == "ALLOW" and risk_level == RiskLevel.LOW:
        return "Responsible"
    if action in ("REWRITE", "CLARIFY"):
        return "Ambiguous — remediation offered"
    if action in ("BLOCK", "REVIEW"):
        return "Risky"
    return "Needs review"
