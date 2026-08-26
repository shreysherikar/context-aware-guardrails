"""Optical path adapter — applies unified sanitization to OCR text + findings.

Reuses P0 OpticalFinding evidence; does not re-run optical analysis.
"""

from __future__ import annotations

from domain.enums import RiskCategory
from domain.models import OpticalFinding
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


def sanitize_optical(
    ocr_text: str,
    findings: list[OpticalFinding],
) -> tuple[str, list[SanitizationFinding]]:
    """Sanitize OCR text using text patterns + remaining optical identifier spans."""
    if not ocr_text:
        return ocr_text, []

    result, san_findings = sanitize_text(ocr_text, source_type="image")

    spans: list[tuple[str, str, RiskCategory, float]] = []
    for finding in findings:
        if not finding.text or finding.type == "prompt_injection":
            continue
        token = _TYPE_TOKEN.get(finding.type)
        if token is None:
            # Skip keyword-only clinical markers (diagnosis, medication, etc.).
            continue
        spans.append((finding.text, token, finding.category, finding.confidence))

    spans.sort(key=lambda s: len(s[0]), reverse=True)
    for span, token, category, confidence in spans:
        cleaned = span.strip()
        if not cleaned:
            continue
        # Extract value after "Label: " if the finding captured a full labeled line.
        value = cleaned
        if ":" in cleaned:
            value = cleaned.split(":", 1)[1].strip()
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
