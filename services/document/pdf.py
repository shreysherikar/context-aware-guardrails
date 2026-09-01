"""Extract text from uploaded PDF documents (pre-guardrail)."""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

DEFAULT_MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 100_000


class DocumentExtractionError(ValueError):
    """Raised when a PDF cannot be read; message is safe for clients."""

    def __init__(self, message: str = "The uploaded document could not be read.") -> None:
        super().__init__(message)
        self.message = message


def extract_pdf_text(data: bytes, *, max_bytes: int = DEFAULT_MAX_PDF_BYTES) -> str:
    """Return plain text from a PDF byte payload."""
    if not data:
        raise DocumentExtractionError("The PDF is empty.")
    if len(data) > max_bytes:
        raise DocumentExtractionError("The PDF exceeds the maximum allowed size (10 MB).")

    try:
        reader = PdfReader(io.BytesIO(data))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
    except PdfReadError as exc:
        raise DocumentExtractionError("The file is not a valid PDF.") from exc
    except OSError as exc:
        raise DocumentExtractionError("The file is not a valid PDF.") from exc

    if not text:
        raise DocumentExtractionError(
            "No readable text found in this PDF. Image-only/scanned PDFs are not supported yet."
        )

    if len(text) > MAX_EXTRACTED_CHARS:
        return f"{text[:MAX_EXTRACTED_CHARS]}\n[Document truncated for analysis]"
    return text
