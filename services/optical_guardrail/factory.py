"""OCR provider factory.

OPTICAL_OCR_PROVIDER selects the implementation:
  - unset / \"mock\" (default) → MockOCRProvider (offline, always available)
  - \"tesseract\" → TesseractOCRProvider (lazy import; extract may fail later)

Unknown values raise at factory call time. Importing this module never
constructs a Tesseract client and never crashes process startup.
"""

from __future__ import annotations

import os

from services.optical_guardrail.ocr import MockOCRProvider, OCRProvider, TesseractOCRProvider


def get_ocr_provider() -> OCRProvider:
    provider = os.getenv("OPTICAL_OCR_PROVIDER", "mock").strip().lower() or "mock"
    if provider == "mock":
        return MockOCRProvider()
    if provider == "tesseract":
        return TesseractOCRProvider()
    raise ValueError(f"Unknown OPTICAL_OCR_PROVIDER={provider!r}. Supported: 'mock', 'tesseract'.")
