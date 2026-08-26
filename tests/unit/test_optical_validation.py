"""Unit tests for optical image validation."""

import io

import pytest
from PIL import Image

from services.optical_guardrail.validation import (
    ImageValidationError,
    validate_image,
)


def _png_bytes(
    size: tuple[int, int] = (8, 8), color: tuple[int, int, int] = (0, 128, 255)
) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(buf, format="JPEG")
    return buf.getvalue()


def test_empty_upload_rejected():
    with pytest.raises(ImageValidationError, match="empty"):
        validate_image(b"")


def test_unsupported_mime_rejected():
    with pytest.raises(ImageValidationError, match="Unsupported"):
        validate_image(_png_bytes(), declared_content_type="application/pdf")


def test_oversized_image_rejected(monkeypatch):
    monkeypatch.setenv("OPTICAL_MAX_IMAGE_BYTES", "10")
    with pytest.raises(ImageValidationError, match="maximum"):
        validate_image(_png_bytes())


def test_valid_png_accepted():
    result = validate_image(_png_bytes(), declared_content_type="image/png")
    assert result.content_type == "image/png"
    assert result.size > 0


def test_valid_jpeg_accepted():
    result = validate_image(_jpeg_bytes(), declared_content_type="image/jpeg")
    assert result.content_type == "image/jpeg"


def test_malformed_bytes_rejected():
    with pytest.raises(ImageValidationError, match="not a valid image"):
        validate_image(b"not-an-image-at-all")
