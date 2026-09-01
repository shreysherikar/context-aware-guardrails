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

import os

from services.optical_guardrail.ocr import (
    DemoOCRProvider,
    MockOCRProvider,
    OCRProvider,
    TesseractOCRProvider,
)
from services.optical_guardrail.ollama_ocr import OllamaOCRProvider


def get_ocr_provider() -> OCRProvider:
    provider = os.getenv("OPTICAL_OCR_PROVIDER", "mock").strip().lower() or "mock"
    if provider == "mock":
        return MockOCRProvider()
    if provider == "demo":
        return DemoOCRProvider()
    if provider == "tesseract":
        return TesseractOCRProvider()
    if provider == "ollama":
        return OllamaOCRProvider()
    raise ValueError(
        f"Unknown OPTICAL_OCR_PROVIDER={provider!r}. "
        "Supported: 'mock', 'demo', 'tesseract', 'ollama'."
    )
