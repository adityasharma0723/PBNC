"""Tests for file validation: magic bytes, size limits, corrupt files."""

import pytest
from app.services.file_validation import validate_file, detect_mime_type
from app.core.errors import FileTooLargeError, UnsupportedMediaError, ValidationError


class TestMagicByteDetection:
    """Verify that MIME type detection uses magic bytes, not extension."""

    def test_detect_pdf(self):
        header = b"%PDF-1.4 fake content"
        assert detect_mime_type(header[:8]) == "application/pdf"

    def test_detect_jpeg(self):
        header = b"\xff\xd8\xff\xe0" + b"\x00" * 4
        assert detect_mime_type(header[:8]) == "image/jpeg"

    def test_detect_png(self):
        header = b"\x89PNG\r\n\x1a\n"
        assert detect_mime_type(header[:8]) == "image/png"

    def test_reject_exe_as_pdf(self):
        """A renamed .exe should be rejected by magic bytes."""
        # MZ header (PE executable)
        exe_header = b"MZ" + b"\x00" * 6
        assert detect_mime_type(exe_header[:8]) is None

    def test_reject_unknown_format(self):
        header = b"\x00\x01\x02\x03\x04\x05\x06\x07"
        assert detect_mime_type(header[:8]) is None


class TestFileValidation:
    """End-to-end file validation tests."""

    def test_empty_file_rejected(self):
        with pytest.raises(ValidationError, match="File too small"):
            validate_file(b"")

    def test_too_small_file_rejected(self):
        with pytest.raises(ValidationError, match="File too small"):
            validate_file(b"\x00\x01\x02")

    def test_unsupported_type_rejected(self):
        """A renamed .exe should fail with UnsupportedMediaError."""
        exe_bytes = b"MZ" + b"\x00" * 100
        with pytest.raises(UnsupportedMediaError):
            validate_file(exe_bytes)

    def test_oversize_file_rejected(self):
        """File exceeding MAX_UPLOAD_SIZE_MB should be rejected."""
        from app.core.config import settings
        original = settings.MAX_UPLOAD_SIZE_MB
        settings.MAX_UPLOAD_SIZE_MB = 0  # 0 MB limit
        try:
            with pytest.raises(FileTooLargeError):
                validate_file(b"%PDF-1.4" + b"\x00" * 100)
        finally:
            settings.MAX_UPLOAD_SIZE_MB = original

    def test_valid_png_accepted(self):
        """Create a minimal valid PNG."""
        import io
        from PIL import Image
        img = Image.new("RGB", (100, 100), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        result = validate_file(png_bytes)
        assert result.mime_type == "image/png"
        assert result.page_count == 1

    def test_valid_jpeg_accepted(self):
        """Create a minimal valid JPEG."""
        import io
        from PIL import Image
        img = Image.new("RGB", (100, 100), "red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        jpeg_bytes = buf.getvalue()

        result = validate_file(jpeg_bytes)
        assert result.mime_type == "image/jpeg"
        assert result.page_count == 1

    def test_corrupt_pdf_rejected(self):
        """PDF magic bytes but corrupt content."""
        corrupt = b"%PDF-1.4 this is not a real pdf"
        with pytest.raises(ValidationError, match="Corrupt"):
            validate_file(corrupt)
