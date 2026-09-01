"""Multimodal safe rewrite — neutralize untrusted instructions, preserve factual data."""

from __future__ import annotations

import re

from services.multimodal.classifier import assess_multimodal_content
from services.multimodal.models import ProcessedMultimodal

_UNTRUSTED_MARKER = "[UNTRUSTED INSTRUCTION REMOVED]"
_AUTHORITY_MARKER = "[UNTRUSTED AUTHORITY CLAIM REMOVED]"
_CREDENTIAL_MARKER = "[CREDENTIAL REDACTED]"
_QR_MARKER = "[UNTRUSTED QR/URL REMOVED — NOT FOR NAVIGATION]"

_INSTRUCTION_LINE = re.compile(
    r"(?im)^.*(?:"
    r"ignore (?:all |previous |prior )?instructions|"
    r"administrator approved|admin approved|security approved|"
    r"upload all (?:data|patient|records)|"
    r"disable (?:guardrail|security|audit|logging)|"
    r"bypass (?:policy|guardrail|firewall|qa|audit)|"
    r"execute (?:command|script|powershell)|"
    r"click (?:the |this )?(?:button|link)|"
    r"important ai instruction|"
    r"emergency override|"
    r"escalate privileges?"
    r").*$"
)

_CREDENTIAL_LINE = re.compile(
    r"(?im).*(?:api[_-]?key|password|secret|token|private key)\s*[:=]\s*\S+.*"
)

_URL_LINE = re.compile(r"(?im)^.*https?://[^\s]+\.onion[^\s]*.*$")


def rewrite_multimodal_content(text: str, *, assessment=None) -> str:
    """Remove/neutralize untrusted instructions while preserving factual content."""
    if not text.strip():
        return text

    lines = text.split("\n")
    kept: list[str] = []
    for line in lines:
        if _INSTRUCTION_LINE.search(line):
            kept.append(_UNTRUSTED_MARKER)
            continue
        if _CREDENTIAL_LINE.search(line):
            kept.append(_CREDENTIAL_MARKER)
            continue
        if _URL_LINE.search(line):
            kept.append(_QR_MARKER)
            continue
        if re.search(r"(?i)administrator approved|admin approved|upload all data", line):
            kept.append(_AUTHORITY_MARKER)
            continue
        kept.append(line)

    result = "\n".join(kept)
    # Collapse duplicate markers
    while _UNTRUSTED_MARKER + "\n" + _UNTRUSTED_MARKER in result:
        result = result.replace(_UNTRUSTED_MARKER + "\n" + _UNTRUSTED_MARKER, _UNTRUSTED_MARKER)

    # Strip instruction blocks
    result = re.sub(
        r"(?is)(?:IMPORTANT AI INSTRUCTION|SYSTEM MESSAGE|DEVELOPER MESSAGE)[^\n]*\n.*?"
        r"(?=(?:\n\n|\Z|Clinical results|Patient|Summary))",
        _UNTRUSTED_MARKER + "\n",
        result,
    )

    if assessment and assessment.qr_detected and assessment.qr_payload:
        result = result.replace(assessment.qr_payload, _QR_MARKER)

    return result.strip()


def process_multimodal_text(
    text: str,
    *,
    source: str = "image",
    is_output: bool = False,
) -> ProcessedMultimodal:
    """Classify → rewrite → mandatory re-classify (fail-closed)."""
    initial = assess_multimodal_content(text, source=source, is_output=is_output)

    if initial.decision == "ALLOW":
        return ProcessedMultimodal(text=text, assessment=initial)

    if initial.decision == "BLOCK":
        safe = (
            "This content cannot be processed because it contains operational instructions "
            "that cannot be treated as authorization or executable guidance."
        )
        return ProcessedMultimodal(text=safe, blocked=True, assessment=initial)

    rewritten = rewrite_multimodal_content(text, assessment=initial)
    recheck = assess_multimodal_content(rewritten, source=source, is_output=is_output)

    if recheck.decision in ("BLOCK", "REWRITE") and recheck.elements:
        # Fail closed — still actionable after rewrite
        if any(e.trust.startswith("UNTRUSTED") for e in recheck.elements):
            safe = (
                "Legitimate informational content was preserved where possible, but embedded "
                "instructions could not be safely neutralized."
            )
            return ProcessedMultimodal(
                text=safe,
                rewrite_applied=True,
                blocked=True,
                assessment=recheck,
            )

    header = "[UNTRUSTED MULTIMODAL DATA — NOT AUTHORITATIVE INSTRUCTIONS]\n"
    return ProcessedMultimodal(
        text=header + rewritten,
        rewrite_applied=True,
        assessment=recheck,
    )
