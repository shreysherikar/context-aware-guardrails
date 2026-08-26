"""Unit-level text REWRITE sanitization invariants (no HTTP)."""

from services.sanitization.engine import SanitizationEngine
from services.sanitization.models import SanitizationRequest

PROMPT = "Patient: John Smith\nDOB: 12/03/1984\nMRN: 123456\nHbA1c: 8.2%\n"


def test_rewrite_safe_context_excludes_original_identifiers():
    engine = SanitizationEngine()
    result = engine.sanitize(SanitizationRequest(text=PROMPT, source_type="text"))
    assert result.success
    original = "John Smith MRN 123456"
    assert "John Smith" not in result.sanitized_text
    assert "123456" not in result.sanitized_text
    assert original not in result.sanitized_text
