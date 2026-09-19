"""Page renderer: converts PDF pages and images into page images + text.

Strategy (documented in ARCHITECTURE.md):
- Digital PDFs: extract text layer via PyMuPDF first. If a page has fewer
  than MIN_TEXT_CHARS, treat it as scanned (no usable text layer).
- All pages are rendered to images at configurable DPI for the LLM.
- Image uploads become a single "page".

This hybrid approach gives cost/accuracy benefits: digital text is cheaper
and more accurate than OCR, but we fall back gracefully to the vision LLM.
"""

import io
import os
import uuid

import fitz  # PyMuPDF
from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def render_pdf_pages(
    pdf_bytes: bytes,
    upload_dir: str | None = None,
) -> list[dict]:
    """Render a PDF into per-page data.

    Returns a list of dicts, one per page:
    {
        "page_number": int (1-indexed),
        "raw_text": str | None,
        "has_text_layer": bool,
        "image_path": str (relative to upload_dir),
        "image_bytes": bytes,
    }
    """
    upload_dir = upload_dir or settings.UPLOAD_DIR
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []

    for i in range(doc.page_count):
        page = doc[i]
        page_number = i + 1

        # Extract text layer
        raw_text = page.get_text("text").strip()
        has_text_layer = len(raw_text) >= settings.MIN_TEXT_CHARS

        # Render page to image at configured DPI
        mat = fitz.Matrix(settings.RENDER_DPI / 72, settings.RENDER_DPI / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")

        # Save image with UUID name
        img_filename = f"{uuid.uuid4().hex}.png"
        img_subdir = img_filename[:2]
        img_dir = os.path.join(upload_dir, "pages", img_subdir)
        os.makedirs(img_dir, exist_ok=True)
        img_path = os.path.join("pages", img_subdir, img_filename)
        abs_path = os.path.join(upload_dir, img_path)

        with open(abs_path, "wb") as f:
            f.write(img_bytes)

        pages.append({
            "page_number": page_number,
            "raw_text": raw_text if has_text_layer else None,
            "has_text_layer": has_text_layer,
            "image_path": img_path,
            "image_bytes": img_bytes,
        })

    doc.close()
    return pages


def render_image_page(
    image_bytes: bytes,
    upload_dir: str | None = None,
) -> dict:
    """Process an uploaded image as a single page.

    Opens with Pillow to validate and normalize, then saves as PNG.
    """
    upload_dir = upload_dir or settings.UPLOAD_DIR
    img = Image.open(io.BytesIO(image_bytes))

    # Convert to RGB if necessary (e.g., RGBA, CMYK)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Save normalized image
    img_filename = f"{uuid.uuid4().hex}.png"
    img_subdir = img_filename[:2]
    img_dir = os.path.join(upload_dir, "pages", img_subdir)
    os.makedirs(img_dir, exist_ok=True)
    img_path = os.path.join("pages", img_subdir, img_filename)
    abs_path = os.path.join(upload_dir, img_path)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    with open(abs_path, "wb") as f:
        f.write(png_bytes)

    return {
        "page_number": 1,
        "raw_text": None,
        "has_text_layer": False,
        "image_path": img_path,
        "image_bytes": png_bytes,
    }
