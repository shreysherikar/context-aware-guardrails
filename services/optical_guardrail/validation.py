"""Image upload validation (pre-OCR).

Rejects empty, oversized, unsupported, or unreadable payloads with safe,
generic error messages. Never executes or persists uploaded bytes.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

# MIME types accepted for P0 optical intake.
ALLOWED_MIME_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
    }
)

# Pillow format names corresponding to allowed MIME types.
_MIME_TO_FORMATS = {
    "image/png": {"PNG"},
    "image/jpeg": {"JPEG"},
    "image/jpg": {"JPEG"},
    "image/webp": {"WEBP"},
}

_FORMAT_TO_MIME = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}

_CHAT_FORMAT_TO_MIME = {
    **_FORMAT_TO_MIME,
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
    "MPO": "image/jpeg",
}

DEFAULT_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


class ImageValidationError(ValueError):
    """Raised when an uploaded image fails validation.

    ``message`` is safe to return to clients (no internals).
    """

    def __init__(self, message: str = "The uploaded image is invalid or unsupported.") -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ValidatedImage:
    """Validated image bytes plus detected MIME (no filesystem path)."""

    data: bytes
    content_type: str
    size: int


def _max_bytes() -> int:
    raw = os.getenv("OPTICAL_MAX_IMAGE_BYTES", "").strip()
    if not raw:
        return DEFAULT_MAX_IMAGE_BYTES
    try:
        value = int(raw)
    except ValueError as exc:
        raise ImageValidationError("Image size limit is misconfigured.") from exc
    if value <= 0:
        raise ImageValidationError("Image size limit is misconfigured.")
    return value


def validate_image(
    data: bytes,
    *,
    declared_content_type: str | None = None,
) -> ValidatedImage:
    """Validate image bytes before OCR.

    Checks emptiness, size, declared MIME (when provided), and that Pillow can
    decode a supported raster format. Does not write to disk.
    """
    if not data:
        raise ImageValidationError("The uploaded image is empty.")

    max_bytes = _max_bytes()
    if len(data) > max_bytes:
        raise ImageValidationError("The uploaded image exceeds the maximum allowed size.")

    if declared_content_type:
        normalized = declared_content_type.split(";")[0].strip().lower()
        if normalized and normalized not in ALLOWED_MIME_TYPES:
            raise ImageValidationError("Unsupported image format.")

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        # verify() leaves the image unusable; reopen for format metadata.
        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or "").upper()
    except UnidentifiedImageError as exc:
        raise ImageValidationError("The uploaded file is not a valid image.") from exc
    except OSError as exc:
        raise ImageValidationError("The uploaded file is not a valid image.") from exc

    if fmt not in _FORMAT_TO_MIME:
        raise ImageValidationError("Unsupported image format.")

    content_type = _FORMAT_TO_MIME[fmt]
    if declared_content_type:
        normalized = declared_content_type.split(";")[0].strip().lower()
        if normalized in ALLOWED_MIME_TYPES:
            allowed_formats = _MIME_TO_FORMATS.get(normalized, set())
            if fmt not in allowed_formats:
                raise ImageValidationError("Image content does not match the declared type.")

    return ValidatedImage(data=data, content_type=content_type, size=len(data))


def validate_chat_image(
    data: bytes,
    *,
    declared_content_type: str | None = None,
) -> ValidatedImage:
    """Permissive image validation for chat uploads (any Pillow-decodable raster)."""
    if not data:
        raise ImageValidationError("The uploaded image is empty.")

    max_bytes = _max_bytes()
    if len(data) > max_bytes:
        raise ImageValidationError("The uploaded image exceeds the maximum allowed size.")

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or "").upper()
    except UnidentifiedImageError as exc:
        raise ImageValidationError("The uploaded file is not a valid image.") from exc
    except OSError as exc:
        raise ImageValidationError("The uploaded file is not a valid image.") from exc

    content_type = _CHAT_FORMAT_TO_MIME.get(fmt)
    if not content_type:
        raise ImageValidationError("Unsupported image format.")

    if declared_content_type:
        normalized = declared_content_type.split(";")[0].strip().lower()
        if normalized and normalized != content_type and normalized not in ALLOWED_MIME_TYPES:
            pass  # trust detected format for chat uploads

    return ValidatedImage(data=data, content_type=content_type, size=len(data))
