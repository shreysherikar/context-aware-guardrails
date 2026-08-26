"""Unit-level optical REWRITE sanitization invariants (no HTTP)."""

from domain.enums import RiskCategory
from domain.models import OpticalFinding
from services.sanitization.engine import SanitizationEngine
from services.sanitization.models import SanitizationRequest

OCR = "Patient: John Smith\nDOB: 12/03/1984\nMRN: 837291\nHbA1c: 8.2%\n"


def test_optical_rewrite_safe_context_excludes_original_ocr_identifiers():
    engine = SanitizationEngine()
    findings = [
        OpticalFinding(
            type="name",
            category=RiskCategory.PII,
            confidence=0.9,
            text="Patient: John Smith",
        ),
        OpticalFinding(
            type="dob",
            category=RiskCategory.PII,
            confidence=0.9,
            text="DOB: 12/03/1984",
        ),
        OpticalFinding(
            type="mrn",
            category=RiskCategory.PHI,
            confidence=0.95,
            text="MRN: 837291",
        ),
    ]
    result = engine.sanitize(
        SanitizationRequest(text=OCR, source_type="image", optical_findings=findings)
    )
    assert result.success
    assert "John Smith" not in result.sanitized_text
    assert "837291" not in result.sanitized_text
    assert "12/03/1984" not in result.sanitized_text
