"""Unit tests for unified text/optical sanitization."""

from domain.enums import RiskCategory
from domain.models import OpticalFinding
from services.sanitization.engine import SanitizationEngine
from services.sanitization.models import SanitizationRequest
from services.sanitization.text import (
    TOKEN_DATE,
    TOKEN_MRN,
    TOKEN_PATIENT,
    sanitize_text,
)

SAMPLE = "Patient: John Smith\nDOB: 12/03/1984\nMRN: 123456\nHbA1c: 8.2%\n"


def test_text_sanitization_redacts_identifiers_keeps_lab_value():
    sanitized, findings = sanitize_text(SAMPLE)
    assert "John Smith" not in sanitized
    assert "12/03/1984" not in sanitized
    assert "123456" not in sanitized
    assert TOKEN_PATIENT in sanitized
    assert TOKEN_DATE in sanitized
    assert TOKEN_MRN in sanitized
    assert "8.2%" in sanitized
    assert "HbA1c" in sanitized
    assert findings


def test_engine_text_success():
    engine = SanitizationEngine()
    result = engine.sanitize(SanitizationRequest(text=SAMPLE, source_type="text"))
    assert result.success
    assert result.changed
    assert result.sanitized_text
    assert "John Smith" not in result.sanitized_text


def test_engine_optical_uses_findings():
    engine = SanitizationEngine()
    findings = [
        OpticalFinding(
            type="name",
            category=RiskCategory.PII,
            confidence=0.9,
            text="Patient: John Smith",
        ),
        OpticalFinding(
            type="mrn",
            category=RiskCategory.PHI,
            confidence=0.95,
            text="MRN: 123456",
        ),
    ]
    result = engine.sanitize(
        SanitizationRequest(
            text=SAMPLE,
            source_type="image",
            optical_findings=findings,
        )
    )
    assert result.success
    assert "John Smith" not in result.sanitized_text
    assert "123456" not in result.sanitized_text
    assert "8.2%" in result.sanitized_text


def test_engine_clean_text_unchanged():
    engine = SanitizationEngine()
    text = "Summarize this public wellness brochure."
    result = engine.sanitize(SanitizationRequest(text=text, source_type="text"))
    assert result.success
    assert result.sanitized_text == text
    assert result.changed is False


def test_engine_failure_returns_unsuccessful_not_original(monkeypatch):
    engine = SanitizationEngine()

    def _boom(*_a, **_k):
        raise RuntimeError("sanitizer exploded")

    monkeypatch.setattr("services.sanitization.engine.sanitize_text", _boom)
    result = engine.sanitize(SanitizationRequest(text=SAMPLE, source_type="text"))
    assert result.success is False
    assert result.sanitized_text == ""
    assert result.failure_reason == "RuntimeError"
    assert "John Smith" not in result.sanitized_text
