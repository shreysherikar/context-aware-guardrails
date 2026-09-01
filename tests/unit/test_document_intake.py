"""Unit tests for unified file intake."""

import io

import pytest
from PIL import Image

from services.document.intake import FileIntakeError, intake_file


def test_intake_rejects_empty_file():
    with pytest.raises(FileIntakeError, match="empty"):
        intake_file(b"", filename="empty.txt")


def test_intake_reads_plain_text():
    intake = intake_file(b"Hello assignment", filename="notes.txt")
    assert intake.kind == "text"
    assert intake.text == "Hello assignment"


def test_intake_routes_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color="red").save(buf, format="PNG")
    intake = intake_file(buf.getvalue(), filename="photo.png")
    assert intake.kind == "image"
    assert intake.image_bytes is not None


def test_intake_rejects_unknown_binary():
    with pytest.raises(FileIntakeError):
        intake_file(bytes(range(256)), filename="binary.bin")
