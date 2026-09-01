"""Build user-facing ExplainableDecision objects from guardrail pipeline outcomes."""

from __future__ import annotations

from domain.enums import PolicyAction, ResolutionType, RiskCategory, RiskLevel
from domain.models import (
    ExplainableDecision,
    LLMStatusStep,
    LLMResult,
    OpticalFinding,
    OutputGuardrailResult,
    PolicyDecision,
    ResolutionPath,
    RiskAssessment,
)
from services.agent.feedback import (
    build_corrections,
    build_issues,
    build_pharma_remediation,
    issues_for_display,
)

_CATEGORY_LABELS: dict[RiskCategory, str] = {
    RiskCategory.PII: "Personally identifiable information",
    RiskCategory.PHI: "Patient health information",
    RiskCategory.OFF_LABEL: "Off-label or promotional content",
    RiskCategory.IP: "Intellectual property",
    RiskCategory.PROMPT_INJECTION: "Prompt manipulation",
    RiskCategory.CYBER_SAFETY: "Cyber safety",
    RiskCategory.AUTHORITY_SPOOFING: "Authority spoofing",
    RiskCategory.DATA_EXFILTRATION: "Data exfiltration",
    RiskCategory.PHISHING: "Phishing or social engineering",
    RiskCategory.MALWARE: "Malware or harmful code",
    RiskCategory.MULTIMODAL_UNTRUSTED: "Untrusted multimodal content",
}

_CANNOT_SELF_RESOLVE_CATEGORIES = {
    RiskCategory.PROMPT_INJECTION,
    RiskCategory.MALWARE,
    RiskCategory.PHISHING,
    RiskCategory.DATA_EXFILTRATION,
}

_REPHRASE_FRIENDLY_CATEGORIES = {
    RiskCategory.PII,
    RiskCategory.OFF_LABEL,
    RiskCategory.IP,
    RiskCategory.PHI,
}

_PIPELINE_FAILURE_POLICY_IDS = {"ERROR-FAIL-CLOSED", "DEFAULT-FAIL-CLOSED", "CLASSIFIER-FAIL-CLOSED"}


def _effective_decision(
    policy_action: PolicyAction,
    *,
    output_flagged: bool = False,
    pipeline_failure: bool = False,
) -> PolicyAction:
    if output_flagged or pipeline_failure:
        return PolicyAction.REVIEW
    if policy_action == PolicyAction.CLARIFY:
        return PolicyAction.REVIEW
    return policy_action


def _primary_category(risk: RiskAssessment, issues: list) -> str:
    for cat in risk.categories:
        if cat != RiskCategory.NONE and cat in _CATEGORY_LABELS:
            return _CATEGORY_LABELS[cat]
    if risk.injection_detected:
        return _CATEGORY_LABELS[RiskCategory.PROMPT_INJECTION]
    if issues:
        return issues[0].title
    if risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return "High-risk content"
    return "General safety"


def _user_reason(
    effective: PolicyAction,
    *,
    pipeline_failure: bool,
    output_flagged: bool,
) -> str:
    if pipeline_failure:
        return (
            "ContextGuard could not safely complete its safety analysis. "
            "Your request has been held for human review."
        )
    if output_flagged:
        return (
            "The generated response was flagged during post-generation safety checks "
            "and was not returned."
        )
    if effective == PolicyAction.ALLOW:
        return "ContextGuard found no blocking safety concerns."
    if effective == PolicyAction.REWRITE:
        return (
            "ContextGuard identified potentially unsafe elements and transformed "
            "the request into a safer form before forwarding."
        )
    if effective == PolicyAction.REVIEW:
        return (
            "ContextGuard could not safely determine whether this request is "
            "appropriate to forward automatically."
        )
    return (
        "This request contains content that cannot be processed safely "
        "and was not forwarded to the language model."
    )


def _resolution_paths(
    effective: PolicyAction,
    risk: RiskAssessment,
    *,
    pipeline_failure: bool,
    clarify_origin: bool = False,
) -> tuple[ResolutionType, str, list[ResolutionPath]]:
    report_path = ResolutionPath(
        type=ResolutionType.REPORT,
        title="Report incorrect decision",
        message="You can report this decision for human evaluation.",
        primary=False,
    )

    if effective == PolicyAction.ALLOW:
        return (
            ResolutionType.NONE,
            "No action is required. Your request was processed normally.",
            [],
        )

    if effective == PolicyAction.REWRITE:
        return (
            ResolutionType.NONE,
            "Sensitive content was already redacted and a safe version was forwarded.",
            [
                ResolutionPath(
                    type=ResolutionType.REPHRASE,
                    title="Fix by rephrasing",
                    message="You may edit and resubmit a cleaner version of your request.",
                    primary=False,
                ),
                report_path,
            ],
        )

    if effective == PolicyAction.REVIEW or pipeline_failure:
        human = ResolutionPath(
            type=ResolutionType.HUMAN_REVIEW,
            title="Human review required",
            message=(
                "ContextGuard could not safely determine whether this request is "
                "appropriate to forward automatically. The prompt has not been sent to the LLM."
            ),
            primary=True,
        )
        paths = [human, report_path]
        primary = ResolutionType.HUMAN_REVIEW
        msg = "Human intervention is required before this request can proceed."
        if clarify_origin:
            rephrase = ResolutionPath(
                type=ResolutionType.REPHRASE,
                title="Fix by rephrasing",
                message=(
                    "This request may be allowed if you clarify the approved context "
                    "and remove ambiguous promotional language."
                ),
                primary=True,
            )
            paths = [rephrase, human, report_path]
            primary = ResolutionType.REPHRASE
            msg = "You may be able to fix this by rephrasing your request."
        return primary, msg, paths

    # BLOCK
    cats = set(risk.categories)
    if (
        risk.injection_detected
        or cats & _CANNOT_SELF_RESOLVE_CATEGORIES
        or risk.risk_level == RiskLevel.CRITICAL
    ):
        cannot = ResolutionPath(
            type=ResolutionType.CANNOT_SELF_RESOLVE,
            title="Request cannot be safely processed",
            message=(
                "This request contains content that cannot be made safe through "
                "minor wording changes. The original prompt was not forwarded to the LLM."
            ),
            primary=True,
        )
        return (
            ResolutionType.CANNOT_SELF_RESOLVE,
            "Changing a few words would not meaningfully address the safety concern.",
            [cannot, report_path],
        )

    rephrase = ResolutionPath(
        type=ResolutionType.REPHRASE,
        title="Fix by rephrasing",
        message=(
            "This request may be allowed if you change parts of the prompt — "
            "clarify legitimate purpose, remove harmful instructions, or ask for "
            "defensive or educational information instead."
        ),
        primary=True,
    )
    human = ResolutionPath(
        type=ResolutionType.HUMAN_REVIEW,
        title="Human review required",
        message=(
            "If you believe this request has a legitimate purpose, you may "
            "request human review. Approval does not bypass safety checks."
        ),
        primary=False,
    )
    paths = [rephrase, human, report_path]
    primary = ResolutionType.REPHRASE
    msg = "You may be able to fix this by rephrasing your request."
    if clarify_origin or cats & _REPHRASE_FRIENDLY_CATEGORIES:
        primary = ResolutionType.REPHRASE
    elif RiskCategory.PHI in cats or RiskCategory.IP in cats:
        primary = ResolutionType.HUMAN_REVIEW
        msg = "This type of request typically requires human review."
        paths = [human, rephrase, report_path]
    return primary, msg, paths


def _safe_suggestions(
    effective: PolicyAction,
    corrections: list,
    clarify_questions: list[str],
    suggested_rewrite: str | None,
) -> list[str]:
    suggestions: list[str] = []
    for fix in corrections:
        if fix.example:
            suggestions.append(f"{fix.title}: {fix.example}")
        else:
            suggestions.append(f"{fix.title}: {fix.description}")
    for q in clarify_questions:
        suggestions.append(q)
    if suggested_rewrite:
        suggestions.append(f'Try asking: "{suggested_rewrite}"')
    if effective == PolicyAction.BLOCK and not suggestions:
        suggestions.extend(
            [
                "Remove actionable harmful instructions.",
                "Ask for defensive, preventive, or educational information instead.",
                "Clarify the legitimate or authorized purpose of your request.",
            ]
        )
    if effective == PolicyAction.REVIEW and not suggestions:
        suggestions.append("Submit the request for human review if it has a legitimate purpose.")
    return suggestions[:6]


def _llm_status(
    effective: PolicyAction,
    *,
    forwarded_to_llm: bool,
    sanitization_occurred: bool,
    output_flagged: bool,
) -> list[LLMStatusStep]:
    if effective == PolicyAction.ALLOW:
        return [
            LLMStatusStep(label="Prompt", status="forwarded"),
            LLMStatusStep(label="ContextGuard", status="completed"),
            LLMStatusStep(
                label="LLM",
                status="completed" if forwarded_to_llm else "not_contacted",
            ),
        ]
    if effective == PolicyAction.REWRITE:
        return [
            LLMStatusStep(label="Original prompt", status="not_forwarded"),
            LLMStatusStep(label="ContextGuard", status="completed"),
            LLMStatusStep(
                label="Sanitized prompt",
                status="forwarded" if sanitization_occurred else "not_forwarded",
            ),
            LLMStatusStep(
                label="LLM",
                status="completed" if forwarded_to_llm else "not_contacted",
            ),
        ]
    if effective == PolicyAction.REVIEW or output_flagged:
        return [
            LLMStatusStep(label="Prompt", status="pending"),
            LLMStatusStep(label="ContextGuard", status="completed"),
            LLMStatusStep(label="LLM", status="not_contacted"),
        ]
    return [
        LLMStatusStep(label="Original prompt", status="not_forwarded"),
        LLMStatusStep(label="ContextGuard", status="completed"),
        LLMStatusStep(label="LLM", status="not_contacted"),
    ]


def build_explainable_decision(
    *,
    request_id: str,
    risk: RiskAssessment,
    decision: PolicyDecision,
    effective_action: PolicyAction | None = None,
    input_type: str = "text",
    optical_findings: list[OpticalFinding] | None = None,
    original_prompt: str | None = None,
    sanitized_prompt: str | None = None,
    llm_result: LLMResult | None = None,
    output_result: OutputGuardrailResult | None = None,
    pipeline_failure: bool = False,
) -> ExplainableDecision:
    """Build a redacted, user-facing explanation from pipeline evidence."""
    output_flagged = bool(output_result and output_result.flagged)
    if decision.policy_id in _PIPELINE_FAILURE_POLICY_IDS:
        pipeline_failure = True

    policy_action = decision.action
    effective = effective_action or _effective_decision(
        policy_action,
        output_flagged=output_flagged,
        pipeline_failure=pipeline_failure,
    )

    issues = build_issues(
        risk,
        input_type=input_type,
        optical_findings=optical_findings,
        original_prompt=original_prompt,
    )
    display_issues = issues_for_display(
        effective if effective != PolicyAction.REVIEW and policy_action == PolicyAction.CLARIFY
        else policy_action,
        issues,
        output_flagged=output_flagged,
    )
    # Do not pass decision to build_corrections — avoids leaking policy rule descriptions.
    corrections = build_corrections(policy_action, display_issues)
    clarify_q, suggested = build_pharma_remediation(original_prompt or "")

    detected = [f"{i.title}: {i.description}" for i in display_issues]
    if pipeline_failure and not detected:
        detected.append("Safety analysis could not be completed reliably.")

    forwarded = bool(
        llm_result
        and llm_result.attempted
        and llm_result.succeeded
        and not output_flagged
        and effective in (PolicyAction.ALLOW, PolicyAction.REWRITE)
    )

    resolution_type, resolution_message, available = _resolution_paths(
        effective,
        risk,
        pipeline_failure=pipeline_failure,
        clarify_origin=policy_action == PolicyAction.CLARIFY,
    )

    return ExplainableDecision(
        request_id=request_id,
        decision=effective,
        forwarded_to_llm=forwarded,
        category=_primary_category(risk, display_issues),
        reason=_user_reason(effective, pipeline_failure=pipeline_failure, output_flagged=output_flagged),
        detected_elements=detected,
        resolution_type=resolution_type,
        resolution_message=resolution_message,
        safe_suggestions=_safe_suggestions(effective, corrections, clarify_q, suggested),
        available_resolutions=available,
        llm_status=_llm_status(
            effective,
            forwarded_to_llm=forwarded,
            sanitization_occurred=sanitized_prompt is not None,
            output_flagged=output_flagged,
        ),
        sanitized_prompt=sanitized_prompt if effective == PolicyAction.REWRITE else None,
        original_prompt_protected=effective in (PolicyAction.BLOCK, PolicyAction.REVIEW),
    )


def build_rephrase_suggestion(
    *,
    risk: RiskAssessment,
    decision: PolicyDecision,
    original_prompt: str,
    input_type: str = "text",
) -> str:
    """Deterministic safer rewrite suggestion — never preserves unsafe instructions."""
    _, suggested = build_pharma_remediation(original_prompt)
    if suggested:
        return suggested

    issues = build_issues(risk, input_type=input_type, original_prompt=original_prompt)
    if any(i.code == "PROMPT_INJECTION" for i in issues) or risk.injection_detected:
        return (
            "Please rephrase your question without instructions to bypass safety rules. "
            "Ask your business question directly."
        )
    if RiskCategory.PII in risk.categories or any(i.code == "PII" for i in issues):
        return (
            "Please resubmit using placeholders instead of real identifiers "
            "(e.g., [NAME], [SSN], [DATE OF BIRTH])."
        )
    if RiskCategory.PHI in risk.categories:
        return (
            "Please use de-identified or aggregated data instead of patient-identifiable details."
        )
    if RiskCategory.OFF_LABEL in risk.categories or decision.action == PolicyAction.CLARIFY:
        return (
            "Please clarify that you need information for an approved indication only, "
            "and cite the source document you are referring to."
        )
    if RiskCategory.IP in risk.categories:
        return (
            "Please ask about publicly available information rather than proprietary "
            "or trade-secret details."
        )
    if RiskCategory.CYBER_SAFETY in risk.categories:
        return (
            "Please ask about defensive cybersecurity practices or legitimate "
            "threat intelligence instead."
        )
    return (
        "Please rephrase your request to focus on a legitimate, authorized, "
        "and compliant purpose."
    )
