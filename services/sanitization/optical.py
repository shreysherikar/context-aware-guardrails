"""Optical path adapter — applies unified sanitization to OCR text + findings.

Reuses P0 OpticalFinding evidence; integrates multimodal safe rewrite.
"""

from __future__ import annotations

from domain.enums import RiskCategory
from domain.models import OpticalFinding
from services.multimodal.rewrite import process_multimodal_text
from services.sanitization.models import SanitizationFinding
from services.sanitization.text import (
    TOKEN_DATE,
    TOKEN_EMAIL,
    TOKEN_GENERIC,
    TOKEN_MRN,
    TOKEN_PATIENT,
    TOKEN_PHONE,
    sanitize_text,
)

_TYPE_TOKEN = {
    "name": TOKEN_PATIENT,
    "dob": TOKEN_DATE,
    "mrn": TOKEN_MRN,
    "patient_id": TOKEN_MRN,
    "email": TOKEN_EMAIL,
    "phone": TOKEN_PHONE,
    "ssn": TOKEN_GENERIC,
    "address": TOKEN_GENERIC,
}

_REDACTION_TOKENS = frozenset(_TYPE_TOKEN.values()) | {TOKEN_GENERIC}

_UNTRUSTED_TYPES = frozenset({
    "prompt_injection",
    "IMAGE_PROMPT_INJECTION",
    "VISUAL_AUTHORITY_SPOOFING",
    "DATA_EXFILTRATION_ATTEMPT",
    "POLICY_BYPASS_ATTEMPT",
    "MALWARE_EXECUTION_ATTEMPT",
    "COMPUTER_USE_MANIPULATION",
    "PHISHING_ATTEMPT",
    "MALICIOUS_URL",
    "PRIVILEGE_ESCALATION_ATTEMPT",
})


def sanitize_optical(
    ocr_text: str,
    findings: list[OpticalFinding],
) -> tuple[str, list[SanitizationFinding]]:
    """Sanitize OCR text: multimodal rewrite + PII span redaction."""
    if not ocr_text:
        return ocr_text, []

    # Multimodal safe rewrite first — neutralize embedded instructions
    processed = process_multimodal_text(ocr_text, source="image")
    if processed.blocked:
        raise RuntimeError("Multimodal content blocked — cannot produce safe representation")
    working_text = processed.text
    san_findings: list[SanitizationFinding] = []
    if processed.rewrite_applied:
        san_findings.append(
            SanitizationFinding(
                entity_type="multimodal_rewrite",
                category=RiskCategory.MULTIMODAL_UNTRUSTED,
                replacement="[UNTRUSTED INSTRUCTION REMOVED]",
                confidence=0.9,
                source="image",
                location="multimodal",
            )
        )

    result, text_findings = sanitize_text(working_text, source_type="image")
    san_findings.extend(text_findings)

    spans: list[tuple[str, str, RiskCategory, float]] = []
    for finding in findings:
        if not finding.text or finding.type in _UNTRUSTED_TYPES:
            continue
        if finding.trust and finding.trust.startswith("UNTRUSTED"):
            continue
        token = _TYPE_TOKEN.get(finding.type)
        if token is None:
            continue
        spans.append((finding.text, token, finding.category, finding.confidence))

    spans.sort(key=lambda s: len(s[0]), reverse=True)
    for span, token, category, confidence in spans:
        cleaned = span.strip()
        if not cleaned:
            continue
        value = cleaned.split(":", 1)[1].strip() if ":" in cleaned else cleaned
        for candidate in (cleaned, value):
            if not candidate or candidate in _REDACTION_TOKENS:
                continue
            if candidate in result:
                result = result.replace(candidate, token)
                san_findings.append(
                    SanitizationFinding(
                        entity_type="optical_span",
                        category=category,
                        replacement=token,
                        confidence=confidence,
                        source="image",
                        location="optical_finding",
                        original_value=candidate,
                    )
                )
                break

    return result, san_findings
