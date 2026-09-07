"""Deterministic issue and correction builders from guardrail outcomes."""

from __future__ import annotations

import re

from domain.enums import PolicyAction, RiskCategory
from domain.models import OpticalFinding, PolicyDecision, RiskAssessment
from services.agent.models import AgentCorrection, AgentIssue, PromptHighlight
from services.agent.pharma_context import pharma_ambiguity_notes, pharma_guidance_for
from services.risk_engine.offensive_patterns import match_offensive_cyber

_CATEGORY_ISSUES: dict[RiskCategory, tuple[str, str, str, str]] = {
    RiskCategory.PROMPT_INJECTION: (
        "PROMPT_INJECTION",
        "Prompt manipulation detected",
        "Your message appears to instruct the system to bypass safety rules or ignore policy.",
        "high",
    ),
    RiskCategory.PII: (
        "PII",
        "Personally identifiable information (PII)",
        "The request contains identifiers such as SSN, date of birth, email, or address.",
        "medium",
    ),
    RiskCategory.PHI: (
        "PHI",
        "Patient health information (PHI)",
        "The request involves patient-identifiable or clinical data that requires extra controls.",
        "high",
    ),
    RiskCategory.OFF_LABEL: (
        "OFF_LABEL",
        "Ambiguous promotional or off-label request",
        "The request may lead to non-compliant promotional language without approved indication, "
        "fair balance, or medical affairs review.",
        "medium",
    ),
    RiskCategory.IP: (
        "IP",
        "Intellectual property exposure",
        "The request may expose proprietary formulas, trade secrets, or unreleased data.",
        "medium",
    ),
    RiskCategory.CYBER_SAFETY: (
        "CYBER_SAFETY",
        "Dark-web access prevention",
        "This request seeks operational guidance for accessing or navigating restricted "
        "dark-web services, which is not permitted.",
        "high",
    ),
    RiskCategory.MALWARE: (
        "MALWARE",
        "Unauthorized hacking or exploit request",
        "The request asks for help hacking, exploiting, writing malware, "
        "or breaking into a system. "
        "Chat cannot assist with that.",
        "high",
    ),
    RiskCategory.PHISHING: (
        "PHISHING",
        "Phishing or credential-harvesting request",
        "The request asks for help creating phishing messages or collecting credentials. "
        "Chat cannot assist with that.",
        "high",
    ),
    RiskCategory.DATA_EXFILTRATION: (
        "DATA_EXFILTRATION",
        "Data theft or dump request",
        "The request asks to steal, leak, or dump data. Chat cannot assist with that.",
        "high",
    ),
}

_ACTION_CORRECTIONS: dict[PolicyAction, list[tuple[str, str, str | None]]] = {
    PolicyAction.BLOCK: [
        (
            "Start over with a compliant request",
            "Remove any attempt to override system instructions, and do not ask for help "
            "hacking, writing malware, phishing, or stealing data. "
            "Ask your business question directly.",
            "Instead of: 'Hack this for me', try: "
            "'How do I report a security issue through our approved channel?'",
        ),
    ],
    PolicyAction.REVIEW: [
        (
            "Route through human review",
            "This type of request cannot be answered automatically. Submit it through your "
            "approved compliance or clinical review channel.",
            None,
        ),
        (
            "Use de-identified data",
            "If you need analysis, remove patient names, MRNs, and direct identifiers first.",
            "Ask about 'aggregated adverse event trends' instead of named patients.",
        ),
    ],
    PolicyAction.CLARIFY: [
        (
            "Clarify the approved context",
            "State whether you need information for an approved indication only, and cite the "
            "source document or study you are referring to.",
            "Example: 'Summarize the approved-label efficacy data from the Phase III CSR.'",
        ),
    ],
    PolicyAction.REWRITE: [
        (
            "Rewrite so chat can answer",
            "The main chat uses the same guardrails. It cannot use this prompt until "
            "direct identifiers and unsafe instructions are removed.",
            "Ask the same task using employee ID, case ID, or placeholders "
            "instead of SSN, DOB, or names.",
        ),
    ],
    PolicyAction.ALLOW: [
        (
            "Request is compliant",
            "No policy issues were detected. Your request was processed normally.",
            None,
        ),
    ],
}


def build_issues(
    risk: RiskAssessment,
    *,
    input_type: str = "text",
    optical_findings: list[OpticalFinding] | None = None,
    original_prompt: str | None = None,
) -> list[AgentIssue]:
    issues: list[AgentIssue] = []
    seen: set[str] = set()

    for category in risk.categories:
        if category == RiskCategory.NONE:
            continue
        meta = _CATEGORY_ISSUES.get(category)
        if meta is None or meta[0] in seen:
            continue
        seen.add(meta[0])
        issues.append(
            AgentIssue(
                code=meta[0],
                title=meta[1],
                description=meta[2],
                severity=meta[3],
            )
        )

    if risk.injection_detected and "PROMPT_INJECTION" not in seen:
        meta = _CATEGORY_ISSUES[RiskCategory.PROMPT_INJECTION]
        issues.append(
            AgentIssue(code=meta[0], title=meta[1], description=meta[2], severity=meta[3])
        )

    if optical_findings:
        finding_types = {f.type for f in optical_findings}
        if finding_types & {"email", "ssn", "dob", "phone", "address", "name"}:
            if "PII" not in seen:
                meta = _CATEGORY_ISSUES[RiskCategory.PII]
                issues.append(
                    AgentIssue(code=meta[0], title=meta[1], description=meta[2], severity=meta[3])
                )
        if finding_types & {"mrn", "patient_id", "diagnosis", "medication", "lab_result"}:
            if "PHI" not in seen:
                meta = _CATEGORY_ISSUES[RiskCategory.PHI]
                issues.append(
                    AgentIssue(code=meta[0], title=meta[1], description=meta[2], severity=meta[3])
                )

    if not issues and risk.risk_level.value not in ("NONE", "LOW"):
        issues.append(
            AgentIssue(
                code="POLICY_RISK",
                title="Policy risk detected",
                description=risk.reasoning or "The request was flagged by the risk classifier.",
                severity="medium",
            )
        )

    if original_prompt:
        for note in pharma_ambiguity_notes(original_prompt):
            if not any(note in i.description for i in issues):
                issues.append(
                    AgentIssue(
                        code="PHARMA_AMBIGUITY",
                        title="Ambiguous pharma request",
                        description=note,
                        severity="medium",
                    )
                )

    if input_type == "image" and not issues:
        issues.append(
            AgentIssue(
                code="OPTICAL_SCAN",
                title="Image content scanned",
                description="The uploaded image was analyzed for sensitive or unsafe content.",
                severity="low",
            )
        )

    return issues


def build_corrections(
    action: PolicyAction,
    issues: list[AgentIssue],
    *,
    decision: PolicyDecision | None = None,
) -> list[AgentCorrection]:
    corrections: list[AgentCorrection] = []
    for title, description, example in _ACTION_CORRECTIONS.get(action, []):
        corrections.append(AgentCorrection(title=title, description=description, example=example))

    if decision and decision.reasons:
        for reason in decision.reasons:
            if not any(reason in c.description for c in corrections):
                corrections.append(
                    AgentCorrection(
                        title="Policy rule applied",
                        description=reason,
                        example=None,
                    )
                )

    if action == PolicyAction.BLOCK and any(i.code == "PII" for i in issues):
        corrections.append(
            AgentCorrection(
                title="Remove direct identifiers",
                description="Delete SSN, full dates of birth, and home addresses from your prompt.",
                example="Replace 'SSN 123-45-6789' with 'employee ID [redacted]'.",
            )
        )

    return corrections


_IDENTIFIER_VALUES = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    re.compile(r"\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b"),
]

_PII_FIELD_REWRITES = [
    (re.compile(r"(?i)social security numbers?"), "employee ID"),
    (re.compile(r"(?i)\bssns?\b"), "employee ID"),
    (re.compile(r"(?i)dates? of birth"), "start date"),
    (re.compile(r"(?i)\bdobs?\b"), "start date"),
    (re.compile(r"(?i)home addresses?"), "work location"),
    (re.compile(r"(?i)email addresses?"), "work contact"),
    (re.compile(r"(?i)patient names?"), "the case ID"),
    (re.compile(r"(?i)medical record numbers?"), "the case ID"),
    (re.compile(r"(?i)\bmrns?\b"), "the case ID"),
]

_INJECTION_CLAUSES = [
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions[^.!?]*[.!?]?"),
    re.compile(r"(?i)pretend you(?:'re| are)\s+(?:an?\s+)?unrestricted[^.!?]*[.!?]?"),
    re.compile(r"(?i)disregard\s+(?:your\s+)?(?:policy|rules|guidelines)[^.!?]*[.!?]?"),
    re.compile(r"(?i)score this as low risk[^.!?]*[.!?]?"),
    re.compile(r"(?i)with no policy limits[^.!?]*[.!?]?"),
]

_JAILBREAK_MARKERS = re.compile(
    r"(?i)\b(ignore|disregard|pretend|jailbreak|unrestricted|no policy)\b"
)


def _clean_rewrite_spacing(text: str) -> str:
    cleaned = re.sub(r"\s*[—–-]\s*(?:\[REDACTED\]|REDACTED)\s*[—–-]?\s*", " ", text)
    cleaned = re.sub(r"\s*[—–]\s*", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip(" \t\n-—")


def build_suggested_prompt(
    original_prompt: str,
    *,
    risk: RiskAssessment,
    decision: PolicyDecision | None = None,
    issues: list[AgentIssue] | None = None,
    input_type: str = "text",
) -> str:
    """Return a prompt the user can actually send through the same chat guardrails."""
    _, pharma = build_pharma_remediation(original_prompt or "")
    if pharma:
        return pharma

    detected = (
        issues
        if issues is not None
        else build_issues(risk, input_type=input_type, original_prompt=original_prompt)
    )
    codes = {i.code for i in detected}
    action = decision.action if decision is not None else PolicyAction.REVIEW
    text = (original_prompt or "").strip()

    if "PROMPT_INJECTION" in codes or risk.injection_detected:
        remainder = text
        for pattern in _INJECTION_CLAUSES:
            remainder = pattern.sub(" ", remainder)
        remainder = _clean_rewrite_spacing(remainder)
        if remainder and not _JAILBREAK_MARKERS.search(remainder) and len(remainder) > 24:
            return remainder
        return (
            "Summarize the approved product or policy information I need for this work task. "
            "Do not change safety rules."
        )

    if (
        "PII" in codes
        or "PHI" in codes
        or RiskCategory.PII in risk.categories
        or RiskCategory.PHI in risk.categories
    ):
        rewritten = text
        for pattern in _IDENTIFIER_VALUES:
            rewritten = pattern.sub("", rewritten)
        for pattern, replacement in _PII_FIELD_REWRITES:
            rewritten = pattern.sub(replacement, rewritten)
        rewritten = _clean_rewrite_spacing(rewritten)
        looks_unsafe = bool(
            re.search(
                r"(?i)\b(ssn|social security|date of birth|\bdob\b|patient name|\bmrn\b)\b",
                rewritten,
            )
        )
        if rewritten and rewritten.lower() != text.lower() and not looks_unsafe:
            return rewritten
        if "PHI" in codes or RiskCategory.PHI in risk.categories:
            return (
                "Summarize this using de-identified or aggregated details only. "
                "Do not include patient names, MRNs, or other identifiers."
            )
        return (
            "Help complete this workplace task using only non-identifying details "
            "such as employee ID, role, and start date. Do not use SSN, date of birth, "
            "or other personal identifiers."
        )

    if "OFF_LABEL" in codes or action == PolicyAction.CLARIFY:
        return (
            "From approved materials only, summarize on-label information for this product. "
            "If medical-affairs review is required, say so instead of drafting off-label claims."
        )
    if "IP" in codes or RiskCategory.IP in risk.categories:
        return (
            "Summarize publicly available information on this topic. "
            "Do not include proprietary formulas, trade secrets, or unreleased data."
        )
    if "CYBER_SAFETY" in codes or RiskCategory.CYBER_SAFETY in risk.categories:
        return (
            "Explain defensive cybersecurity practices or legitimate threat-awareness guidance. "
            "Do not provide instructions for accessing restricted or illicit services."
        )
    if "MALWARE" in codes or RiskCategory.MALWARE in risk.categories:
        return (
            "How do I report a suspected security issue through our approved internal channel? "
            "Do not ask for exploit steps or unauthorized access."
        )
    if "PHISHING" in codes or RiskCategory.PHISHING in risk.categories:
        return (
            "How should employees report a suspected suspicious email "
            "through our approved channel? "
            "Do not ask for help collecting credentials or imitating a login page."
        )
    if "DATA_EXFILTRATION" in codes or RiskCategory.DATA_EXFILTRATION in risk.categories:
        return (
            "How do I request an approved data export through the official records process? "
            "Do not ask to copy records outside approved systems."
        )
    return (
        "Rephrase this as a legitimate workplace request using only approved, "
        "non-sensitive information."
    )


# Patterns used to highlight problematic spans in the user's original prompt.
_HIGHLIGHT_RULES: list[tuple[re.Pattern[str], str, str, str]] = [
    (
        re.compile(r"(?i)\bignore\s+(all\s+)?(previous|prior)\s+instructions\b"),
        "PROMPT_INJECTION",
        "Instruction override attempt",
        "high",
    ),
    (
        re.compile(r"(?i)\bpretend you(?:'re| are)\s+(?:an?\s+)?unrestricted\b"),
        "PROMPT_INJECTION",
        "Attempts to bypass safety rules",
        "high",
    ),
    (
        re.compile(r"(?i)\bdisregard\s+(?:your\s+)?(?:policy|rules|guidelines)\b"),
        "PROMPT_INJECTION",
        "Policy bypass language",
        "high",
    ),
    (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "PII",
        "Social Security Number — remove before submitting",
        "high",
    ),
    (
        re.compile(r"(?i)\b(?:ssn|social security)\b"),
        "PII",
        "Social Security reference — use a redacted placeholder",
        "medium",
    ),
    (
        re.compile(r"(?i)\b(?:date of birth|dob)\b"),
        "PII",
        "Date of birth is personally identifiable",
        "medium",
    ),
    (
        re.compile(r"(?i)\b(?:patient name|mrn|medical record)\b"),
        "PHI",
        "Patient-identifiable health information",
        "high",
    ),
    (
        re.compile(r"(?i)\boff[- ]label\b"),
        "OFF_LABEL",
        "Off-label use requires medical affairs review",
        "medium",
    ),
    (
        re.compile(r"(?i)\b(?:proprietary formula|trade secret)\b"),
        "IP",
        "May expose intellectual property",
        "medium",
    ),
    (
        re.compile(r"(?i)(?:api[_-]?key|password|secret|token)\s*[:=]\s*\S+"),
        "CREDENTIAL",
        "Credential or secret detected",
        "high",
    ),
]


def build_prompt_highlights(
    original_prompt: str | None,
    issues: list[AgentIssue],
) -> list[PromptHighlight]:
    """Find spans in the user prompt that explain why guardrails fired."""
    if not original_prompt:
        return []

    highlights: list[PromptHighlight] = []
    seen_spans: set[tuple[int, int]] = set()

    _offense_reason = {
        RiskCategory.MALWARE: (
            "MALWARE",
            "Unauthorized hacking, malware, or exploit request — cannot be used in chat",
            "high",
        ),
        RiskCategory.PHISHING: (
            "PHISHING",
            "Phishing or credential-harvesting request — cannot be used in chat",
            "high",
        ),
        RiskCategory.DATA_EXFILTRATION: (
            "DATA_EXFILTRATION",
            "Data theft or dump request — cannot be used in chat",
            "high",
        ),
        RiskCategory.PROMPT_INJECTION: (
            "PROMPT_INJECTION",
            "Attempts to bypass safety rules",
            "high",
        ),
    }
    for category, matched, start, end in match_offensive_cyber(original_prompt):
        span = (start, end)
        if span in seen_spans:
            continue
        meta = _offense_reason.get(category)
        if meta is None:
            continue
        seen_spans.add(span)
        highlights.append(
            PromptHighlight(
                start=start,
                end=end,
                text=matched,
                code=meta[0],
                reason=meta[1],
                severity=meta[2],
            )
        )

    for pattern, code, reason, severity in _HIGHLIGHT_RULES:
        for match in pattern.finditer(original_prompt):
            span = (match.start(), match.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            highlights.append(
                PromptHighlight(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(0),
                    code=code,
                    reason=reason,
                    severity=severity,
                )
            )

    # Tie highlights to detected issue codes when patterns missed edge cases.
    issue_codes = {i.code for i in issues}
    if issue_codes and not highlights:
        highlights.append(
            PromptHighlight(
                start=0,
                end=min(len(original_prompt), 120),
                text=original_prompt[:120],
                code=next(iter(issue_codes)),
                reason=issues[0].description,
                severity=issues[0].severity,
            )
        )

    return sorted(highlights, key=lambda h: h.start)


def issues_for_display(
    action: PolicyAction,
    issues: list[AgentIssue],
    *,
    output_flagged: bool = False,
) -> list[AgentIssue]:
    """Hide guardrail metadata during normal compliant chat."""
    if action == PolicyAction.ALLOW and not output_flagged:
        return []
    return [i for i in issues if i.code != "OPTICAL_SCAN"]


def guardrail_was_triggered(
    action: PolicyAction,
    issues: list[AgentIssue],
    *,
    output_flagged: bool = False,
    blocked: bool = False,
    review_required: bool = False,
) -> bool:
    if blocked or review_required or output_flagged:
        return True
    if action != PolicyAction.ALLOW:
        return True
    return len(issues) > 0


def compose_deterministic_message(
    *,
    action: PolicyAction,
    issues: list[AgentIssue],
    corrections: list[AgentCorrection],
    answer: str | None = None,
    sanitized_text: str | None = None,
    output_flagged: bool = False,
    clarification_questions: list[str] | None = None,
    suggested_rewrite: str | None = None,
) -> str:
    """Build a plain-language agent message without calling an LLM."""
    # Normal chatbot mode: compliant requests get the answer only.
    if action == PolicyAction.ALLOW and answer and not output_flagged and not issues:
        return answer

    if action == PolicyAction.ALLOW and answer and not output_flagged:
        return answer

    parts: list[str] = []

    if action == PolicyAction.ALLOW and not output_flagged:
        if answer:
            parts.append(answer)
        else:
            parts.append(
                "I couldn't generate a response right now. Please check that Ollama is "
                "running (`ollama serve`) and that the model in your .env (OLLAMA_MODEL) "
                "is installed (`ollama pull llama3.2:3b`)."
            )
    elif action == PolicyAction.REWRITE:
        parts.append(
            "I noticed sensitive details in your request, so I handled a redacted version. "
            "Here is what I can share:"
        )
    elif action == PolicyAction.BLOCK:
        parts.append(
            "I am not able to help with this request as written because it could lead to "
            "a policy or compliance issue."
        )
    elif action == PolicyAction.REVIEW or output_flagged:
        parts.append(
            "This needs a compliance or clinical review before I can respond. "
            "I have paused here to protect patients and the company."
        )
    elif action == PolicyAction.CLARIFY:
        parts.append(
            "Your request could be interpreted in a few different ways, and some of those "
            "could be non-compliant. I need a bit more clarity before proceeding."
        )

    if issues:
        parts.append("\nWhat I flagged:")
        for issue in issues:
            parts.append(f"• {issue.title} — {issue.description}")

    if clarification_questions:
        parts.append("\nCould you clarify:")
        for q in clarification_questions:
            parts.append(f"• {q}")

    if suggested_rewrite:
        parts.append(f'\nTry asking it this way:\n"{suggested_rewrite}"')

    if corrections:
        parts.append("\nHow to fix it:")
        for fix in corrections:
            line = f"• {fix.title}: {fix.description}"
            if fix.example:
                line += f" For example: {fix.example}"
            parts.append(line)

    if sanitized_text and action == PolicyAction.REWRITE:
        parts.append(f"\n(Safe version used: {sanitized_text})")

    if answer and action in (PolicyAction.REWRITE,) and not output_flagged:
        parts.append(f"\n{answer}")

    return "\n".join(parts)


def build_pharma_remediation(original_prompt: str) -> tuple[list[str], str | None]:
    guidance = pharma_guidance_for(original_prompt)
    if guidance is None:
        return [], None
    return guidance.clarification_questions, guidance.suggested_rewrite
