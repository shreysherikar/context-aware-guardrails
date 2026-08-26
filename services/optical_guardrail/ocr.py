"""OCR provider abstraction.

Providers extract text from image bytes. They produce OCRResult evidence only
and never decide policy actions. The default MockOCRProvider needs no system
binaries and never fails application startup.
"""

from __future__ import annotations

import io
import logging
from typing import Protocol

from domain.models import OCRResult

logger = logging.getLogger(__name__)


class OCRError(RuntimeError):
    """Raised when OCR cannot complete. Safe message only for callers."""

    def __init__(
        self,
        message: str = "Optical text extraction is temporarily unavailable.",
    ) -> None:
        super().__init__(message)
        self.message = message


class OCRProvider(Protocol):
    async def extract(self, image: bytes) -> OCRResult:
        """Extract text from image bytes."""
        ...


class MockOCRProvider:
    """Deterministic offline OCR for local/dev/tests.

    Returns a fixed or caller-configured string. Does not inspect pixels.
    Tests monkeypatch ``default_text`` or replace the provider entirely.
    """

    def __init__(self, default_text: str = "") -> None:
        self.default_text = default_text

    async def extract(self, image: bytes) -> OCRResult:
        if not image:
            raise OCRError("Cannot extract text from an empty image.")
        text = self.default_text
        confidence = 1.0 if text else 0.0
        return OCRResult(text=text, confidence=confidence, entities=[])


class TesseractOCRProvider:
    """Local Tesseract OCR (optional). Lazy-imports pytesseract + Pillow.

    Construction does not require Tesseract to be present; failure surfaces
    only when ``extract`` is called, so the app can still start with mock OCR.
    """

    async def extract(self, image: bytes) -> OCRResult:
        if not image:
            raise OCRError("Cannot extract text from an empty image.")
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            logger.warning("Tesseract OCR dependencies are not installed")
            raise OCRError() from exc

        try:
            with Image.open(io.BytesIO(image)) as img:
                text = pytesseract.image_to_string(img) or ""
        except Exception as exc:  # noqa: BLE001 - fail closed, no provider leak
            logger.exception("Tesseract OCR failed")
            raise OCRError() from exc

        text = text.strip()
        return OCRResult(text=text, confidence=0.7 if text else 0.0, entities=[])
