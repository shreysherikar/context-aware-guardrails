"""Specialist agent definitions for FieldAssist."""

from __future__ import annotations

from services.agent.persona import PHARMA_ASSISTANT_SYSTEM
from services.agent.specialists.base import SpecialistDefinition

COMPLIANCE_GUARD = SpecialistDefinition(
    id="compliance_guard",
    name="Compliance Guard",
    description="Runs risk classification and policy enforcement before any specialist.",
    system_addendum="",
    priority=100,
)

GENERAL_AGENT = SpecialistDefinition(
    id="general",
    name="General Assistant",
    description="Default FieldAssist colleague for broad internal questions.",
    system_addendum=(
        "Handle the request as a general internal pharma assistant. "
        "Stay practical and policy-aware."
    ),
    priority=1,
)

RESEARCH_AGENT = SpecialistDefinition(
    id="research",
    name="Research Agent",
    description="Searches the public web and grounds answers in cited sources.",
    system_addendum=(
        "You are the Research Agent. Prioritize factual, cited answers from the "
        "provided web snippets. Clearly separate public background from approved "
        "internal claims. Say when sources are insufficient."
    ),
    patterns=(
        r"\bsearch (the )?(web|internet)\b",
        r"\blook up\b",
        r"\bfind (online|on the web)\b",
        r"\blatest (news|updates|on|guidance)\b",
        r"\bcurrent (news|status|regulation)\b",
        r"\bwhat(?:'s| is) (?:the )?latest\b",
        r"\bnews about\b",
        r"\bonline research\b",
        r"\bfda\b",
        r"\bregulatory (update|news|guidance)\b",
    ),
    priority=20,
    is_enrichment=True,
)

HCP_ENGAGEMENT_AGENT = SpecialistDefinition(
    id="hcp_engagement",
    name="HCP Engagement Agent",
    description="Drafts compliant outreach, follow-ups, and HCP communication.",
    system_addendum=(
        "You are the HCP Engagement Agent. Focus on compliant outreach, meeting "
        "follow-ups, and professional tone. Never include patient identifiers. "
        "Use neutral, non-promotional language unless approved claims are provided."
    ),
    patterns=(
        r"\bhcp\b",
        r"\bhealthcare provider\b",
        r"\bphysician\b",
        r"\boutreach\b",
        r"\bfollow[- ]?up\b",
        r"\bemail template\b",
        r"\bmeeting (recap|summary|request)\b",
        r"\bdraft (a |an )?(email|message|letter)\b",
        r"\bengagement (plan|strategy)\b",
    ),
    priority=15,
)

ANALYTICS_AGENT = SpecialistDefinition(
    id="analytics",
    name="Analytics Agent",
    description="Summarizes aggregate CRM and campaign performance.",
    system_addendum=(
        "You are the Analytics Agent. Summarize aggregate KPIs, trends, and "
        "segment comparisons only. Never surface individual HCP or patient "
        "identifiers. Call out when data is missing or assumptions are needed."
    ),
    patterns=(
        r"\bcrm\b",
        r"\bkpi\b",
        r"\baggregate\b",
        r"\bcampaign\b",
        r"\bperformance (by|across)\b",
        r"\bsummar(?:y|ize).*(?:region|channel|engagement)\b",
        r"\bengagement (data|metrics|performance)\b",
        r"\bchannel mix\b",
        r"\bconversion rate\b",
    ),
    priority=15,
)

COMPLIANCE_COACH_AGENT = SpecialistDefinition(
    id="compliance_coach",
    name="Compliance Coach",
    description="Explains policy, fair balance, and approved-claim requirements.",
    system_addendum=(
        "You are the Compliance Coach. Explain what is allowed, what needs "
        "medical/legal review, and how to rephrase safely. Be educational, not punitive."
    ),
    patterns=(
        r"\bcompliance\b",
        r"\bpolicy\b",
        r"\bfair balance\b",
        r"\bapproved claim\b",
        r"\bmlr\b",
        r"\bmedical (affairs|review)\b",
        r"\bregulatory\b",
        r"\boff[- ]label\b",
        r"\bpromotional\b",
    ),
    priority=22,
)

OPTICAL_AGENT = SpecialistDefinition(
    id="optical",
    name="Optical Analysis Agent",
    description="Interprets text extracted from uploaded document images.",
    system_addendum=(
        "You are the Optical Analysis Agent. Work from OCR text extracted from "
        "an uploaded image. Flag PHI/PII patterns and describe document content "
        "without inventing fields that are not present."
    ),
    input_types=("image",),
    priority=25,
)

ALL_SPECIALISTS: tuple[SpecialistDefinition, ...] = (
    COMPLIANCE_GUARD,
    GENERAL_AGENT,
    RESEARCH_AGENT,
    HCP_ENGAGEMENT_AGENT,
    ANALYTICS_AGENT,
    COMPLIANCE_COACH_AGENT,
    OPTICAL_AGENT,
)

SPECIALIST_BY_ID = {spec.id: spec for spec in ALL_SPECIALISTS}

SHARED_BASE_PROMPT = PHARMA_ASSISTANT_SYSTEM
