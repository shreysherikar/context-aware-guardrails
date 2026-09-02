"""Ollama vision OCR — extracts text from images using a local vision model."""

from __future__ import annotations

import base64
import logging
import os

from domain.models import OCRResult
from services.llm.ollama_client import OllamaError, chat
from services.optical_guardrail.ocr import OCRError

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "OCR task: transcribe every line of text in this image exactly as printed. "
    "Preserve line breaks. Output only the raw transcribed text with no descriptions, "
    "commentary, or markdown."
)


def _vision_model() -> str:
    return os.getenv("OLLAMA_VISION_MODEL", "") or os.getenv("OLLAMA_MODEL", "qwen3.6:latest")


class OllamaOCRProvider:
    """Vision-model OCR via Ollama (no Tesseract required)."""

    async def extract(self, image: bytes) -> OCRResult:
        if not image:
            raise OCRError("Cannot extract text from an empty image.")

        encoded = base64.b64encode(image).decode("ascii")
        try:
            text = chat(
                [
                    {
                        "role": "user",
                        "content": _EXTRACT_PROMPT,
                        "images": [encoded],
                    }
                ],
                model=_vision_model(),
            )
        except OllamaError as exc:
            logger.warning("Ollama vision OCR failed: %s", exc)
            raise OCRError(
                "Optical text extraction failed. Ensure Ollama is running with a vision model."
            ) from exc

        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        confidence = 0.85 if cleaned else 0.0
        return OCRResult(text=cleaned, confidence=confidence, entities=[])
