"""File validation service.

Security-critical: validates uploads by magic bytes (not extension or
Content-Type header, both of which are trivially spoofable). Also checks
file size, PDF page count, PDF encryption, and Pillow decompression bombs.

Magic byte signatures:
  PDF:  %PDF (25 50 44 46)
  JPEG: FF D8 FF
  PNG:  89 50 4E 47 0D 0A 1A 0A
"""

import io
from dataclasses import dataclass

import fitz
from PIL import Image

from app.core.config import settings
from app.core.errors import FileTooLargeError, UnsupportedMediaError, ValidationError

Image.MAX_IMAGE_PIXELS = 178_956_970

MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
}

ALLOWED_MIMES = set(MAGIC_SIGNATURES.keys())

@dataclass
class FileValidationResult:
    mime_type: str
    size_bytes: int
    page_count: int

def detect_mime_type(header: bytes) -> str | None:
    """Detect MIME type from magic bytes (first 8 bytes are sufficient)."""
    for mime, signatures in MAGIC_SIGNATURES.items():
        for sig in signatures:
            if header[: len(sig)] == sig:
                return mime
    return None

def validate_file(file_bytes: bytes) -> FileValidationResult:
    """Validate an uploaded file. Raises on any issue.

    Steps:
    1. Size check
    2. Magic byte detection
    3. For PDFs: page count, encryption check, corruption check
    4. For images: Pillow open to catch decompression bombs
    """
    size = len(file_bytes)
    if size > settings.max_upload_bytes:
        raise FileTooLargeError(settings.MAX_UPLOAD_SIZE_MB)

    if size < 8:
        raise ValidationError("File too small to be valid")

    mime = detect_mime_type(file_bytes[:8])
    if mime is None or mime not in ALLOWED_MIMES:
        raise UnsupportedMediaError(mime or "unknown")

    page_count = 1

    if mime == "application/pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception:
            raise ValidationError("Corrupt or unreadable PDF")

        if doc.is_encrypted:
            doc.close()
            raise ValidationError("Encrypted PDFs are not supported")

        page_count = doc.page_count
        doc.close()

        if page_count == 0:
            raise ValidationError("PDF has no pages")

        if page_count > settings.MAX_PAGES:
            raise ValidationError(f"PDF exceeds {settings.MAX_PAGES} page limit ({page_count} pages)")

    elif mime.startswith("image/"):
        try:
            img = Image.open(io.BytesIO(file_bytes))
            img.verify()
        except Image.DecompressionBombError:
            raise ValidationError("Image exceeds maximum pixel limit (possible decompression bomb)")
        except Exception:
            raise ValidationError("Corrupt or unreadable image file")

    return FileValidationResult(mime_type=mime, size_bytes=size, page_count=page_count)
