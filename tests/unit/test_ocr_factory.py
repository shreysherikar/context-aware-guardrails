from services.optical_guardrail.factory import get_ocr_provider
from services.optical_guardrail.ocr import MockOCRProvider


def test_ollama_loopback_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("OPTICAL_OCR_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    provider = get_ocr_provider()
    assert isinstance(provider, MockOCRProvider)


def test_mock_ocr_is_default(monkeypatch):
    monkeypatch.setenv("OPTICAL_OCR_PROVIDER", "mock")
    provider = get_ocr_provider()
    assert isinstance(provider, MockOCRProvider)
