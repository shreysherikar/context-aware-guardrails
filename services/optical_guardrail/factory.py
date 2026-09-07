"""OCR provider factory.

OPTICAL_OCR_PROVIDER selects the implementation:
  - unset / \"mock\" (default) → MockOCRProvider (offline, always available)
  - \"tesseract\" → TesseractOCRProvider (lazy import; extract may fail later)
  - \"ollama\" → OllamaOCRProvider (local vision model via Ollama)
  - \"demo\" → DemoOCRProvider (instant OCR for bundled sample images)

Unknown values raise at factory call time. Importing this module never
constructs a Tesseract client and never crashes process startup.
"""

from __future__ import annotations

import logging
import os

from services.optical_guardrail.ocr import (
    DemoOCRProvider,
    MockOCRProvider,
    OCRProvider,
    TesseractOCRProvider,
)
from services.optical_guardrail.ollama_ocr import OllamaOCRProvider


def _is_loopback_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(token in lowered for token in ("127.0.0.1", "localhost", "[::1]", "::1"))


def get_ocr_provider() -> OCRProvider:
    provider = os.getenv("OPTICAL_OCR_PROVIDER", "mock").strip().lower() or "mock"
    if provider == "mock":
        return MockOCRProvider()
    if provider == "demo":
        return DemoOCRProvider()
    if provider == "tesseract":
        return TesseractOCRProvider()
    if provider == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        if _is_loopback_url(base):
            logging.getLogger(__name__).warning(
                "OPTICAL_OCR_PROVIDER=ollama with loopback OLLAMA_BASE_URL=%s; "
                "using mock OCR (localhost is not reachable from ECS).",
                base,
            )
            return MockOCRProvider()
        return OllamaOCRProvider()
    raise ValueError(
        f"Unknown OPTICAL_OCR_PROVIDER={provider!r}. "
        "Supported: 'mock', 'demo', 'tesseract', 'ollama'."
    )
