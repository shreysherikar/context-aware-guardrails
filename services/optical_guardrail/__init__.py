"""Optical / multimodal guardrail (evidence plane only).

OCR and optical analysis produce structured findings that are normalized into
a RiskAssessment. They never produce a PolicyDecision — that remains the sole
authority of the deterministic PolicyEngine.
"""

from services.optical_guardrail.analyzer import OpticalAnalyzer, analyze_ocr
from services.optical_guardrail.factory import get_ocr_provider
from services.optical_guardrail.normalizer import normalize_optical_assessment
from services.optical_guardrail.ocr import MockOCRProvider, OCRProvider
from services.optical_guardrail.sanitizer import sanitize_ocr_text
from services.optical_guardrail.validation import ImageValidationError, validate_image

__all__ = [
    "ImageValidationError",
    "MockOCRProvider",
    "OCRProvider",
    "OpticalAnalyzer",
    "analyze_ocr",
    "get_ocr_provider",
    "normalize_optical_assessment",
    "sanitize_ocr_text",
    "validate_image",
]
