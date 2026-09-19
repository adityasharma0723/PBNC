"""Safe file storage service.

Security notes:
- Files are stored with server-generated UUID names, never the client filename.
  This prevents path-traversal attacks.
- The upload directory is not served by the web server; files are read through
  the API with auth checks.
- sha256 is computed for integrity and deduplication detection.
"""

import hashlib
import os
import uuid

from app.core.config import settings


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_file(data: bytes, extension: str) -> tuple[str, str]:
    """Store file with a UUID name. Returns (stored_path, sha256).

    The stored_path is relative to UPLOAD_DIR for portability.
    """
    sha256 = compute_sha256(data)
    filename = f"{uuid.uuid4().hex}{extension}"
    subdir = filename[:2]  # Shard into subdirectories to avoid inode exhaustion

    dir_path = os.path.join(settings.UPLOAD_DIR, subdir)
    os.makedirs(dir_path, exist_ok=True)

    file_path = os.path.join(dir_path, filename)
    with open(file_path, "wb") as f:
        f.write(data)

    # Return relative path from UPLOAD_DIR
    stored_path = os.path.join(subdir, filename)
    return stored_path, sha256


def get_absolute_path(stored_path: str) -> str:
    """Resolve a stored_path to its absolute filesystem path."""
    return os.path.join(settings.UPLOAD_DIR, stored_path)


def delete_file(stored_path: str) -> None:
    """Delete a stored file. Ignores missing files."""
    abs_path = get_absolute_path(stored_path)
    try:
        os.remove(abs_path)
    except FileNotFoundError:
        pass


def get_extension_for_mime(mime_type: str) -> str:
    """Map MIME type to file extension."""
    return {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
    }.get(mime_type, ".bin")
