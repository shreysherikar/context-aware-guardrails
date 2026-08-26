"""SanitizationEngine — unified safe-context production for REWRITE.

Fail-closed: any unexpected error becomes SanitizationError / unsuccessful
result. Callers must NOT fall back to the original sensitive text.
"""

from __future__ import annotations

import logging

from services.sanitization.models import (
    SANITIZER_VERSION,
    SanitizationRequest,
    SanitizationResult,
)
from services.sanitization.optical import sanitize_optical
from services.sanitization.text import sanitize_text

logger = logging.getLogger(__name__)


class SanitizationError(RuntimeError):
    """Raised when sanitization cannot guarantee a safe representation."""

    def __init__(self, message: str = "Sanitization failed.") -> None:
        super().__init__(message)
        self.message = message


class SanitizationEngine:
    """Provider-independent sanitization. No policy authority."""

    version = SANITIZER_VERSION

    def sanitize(self, request: SanitizationRequest) -> SanitizationResult:
        """Produce sanitized text. On failure returns success=False (fail-closed).

        Never returns the original sensitive text as a "successful" result when
        an error occurred — callers must treat success=False as REVIEW.
        """
        try:
            if request.source_type == "image":
                sanitized, findings = sanitize_optical(
                    request.text,
                    request.optical_findings,
                )
            else:
                sanitized, findings = sanitize_text(
                    request.text,
                    source_type="text",
                )

            if sanitized is None:
                return SanitizationResult(
                    sanitized_text="",
                    sanitized=False,
                    findings=[],
                    changed=False,
                    success=False,
                    failure_reason="invalid_output",
                    source_type=request.source_type,
                    sanitizer_version=self.version,
                )

            changed = sanitized != request.text
            return SanitizationResult(
                sanitized_text=sanitized,
                sanitized=True,
                findings=findings,
                changed=changed,
                success=True,
                failure_reason=None,
                source_type=request.source_type,
                sanitizer_version=self.version,
                metadata={"finding_count": len(findings)},
            )
        except Exception as exc:  # noqa: BLE001 - fail closed
            logger.exception("Sanitization engine failure")
            return SanitizationResult(
                sanitized_text="",
                sanitized=False,
                findings=[],
                changed=False,
                success=False,
                failure_reason=type(exc).__name__,
                source_type=request.source_type,
                sanitizer_version=self.version,
            )
