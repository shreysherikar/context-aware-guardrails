"""Sanitize OCR text by redacting optical findings before any LLM call.

P1: delegates to the unified SanitizationEngine. Kept for backward-compatible
imports from the optical package.
"""

from __future__ import annotations

from domain.models import OpticalFinding
from services.sanitization.models import SanitizationRequest
from services.sanitization.optical import sanitize_optical


def sanitize_ocr_text(ocr_text: str, findings: list[OpticalFinding]) -> str:
    """Return OCR text with sensitive spans replaced by typed redaction tokens.

    Raises RuntimeError if sanitization cannot produce a safe representation
    (callers should fail closed to REVIEW — never pass original OCR to the LLM).
    """
    request = SanitizationRequest(
        text=ocr_text,
        source_type="image",
        optical_findings=findings,
    )
    # Direct optical path (same engine logic) for the string-only helper.
    sanitized, _findings = sanitize_optical(request.text, request.optical_findings)
    if sanitized is None:
        raise RuntimeError("Sanitization produced invalid output.")
    return sanitized
