"""Unit tests for PDF text extraction."""

import pytest

from services.document.pdf import DocumentExtractionError, extract_pdf_text


def test_extract_pdf_rejects_empty_bytes():
    with pytest.raises(DocumentExtractionError, match="empty"):
        extract_pdf_text(b"")


def test_extract_pdf_rejects_invalid_bytes():
    with pytest.raises(DocumentExtractionError):
        extract_pdf_text(b"not a pdf")


def test_extract_pdf_reads_text(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "Assignment content"

    class FakeReader:
        def __init__(self, _buf):
            self.pages = [FakePage()]

    monkeypatch.setattr("services.document.pdf.PdfReader", FakeReader)
    assert extract_pdf_text(b"%PDF-fake") == "Assignment content"
