"""Page quality assessment using image heuristics.

Provides a quality score (0.0-1.0) based on:
- Blur detection via Laplacian variance
- Resolution adequacy (pixels per page dimension)
- Rotation detection (simple heuristic via aspect ratio anomalies)

The score is used by confidence.py to adjust question confidence.
Low-quality pages generate review items.
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageFilter

from app.core.logging import get_logger

logger = get_logger(__name__)

# Thresholds (could be env-configurable, but these are sensible defaults)
BLUR_THRESHOLD = 100.0  # Laplacian variance below this = blurry
MIN_RESOLUTION = 150  # Minimum effective DPI (pixels / inch equivalent)
MIN_DIMENSION = 500  # Minimum pixel dimension for either axis


@dataclass
class QualityResult:
    score: float  # 0.0 (terrible) to 1.0 (excellent)
    blur_score: float
    resolution_adequate: bool
    possibly_rotated: bool
    flags: list[str]


def assess_quality(image_bytes: bytes) -> QualityResult:
    """Assess the quality of a page image.

    Uses Pillow for analysis (no OpenCV dependency needed).
    The Laplacian variance is approximated using Pillow's edge-detection
    filter followed by pixel variance calculation.
    """
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "L":
        gray = img.convert("L")
    else:
        gray = img

    width, height = img.size
    flags: list[str] = []

    # --- Blur detection ---
    # Apply FIND_EDGES filter (Laplacian-like) and compute variance
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_pixels = list(edges.getdata())
    n = len(edge_pixels)
    if n > 0:
        mean = sum(edge_pixels) / n
        variance = sum((p - mean) ** 2 for p in edge_pixels) / n
    else:
        variance = 0.0

    blur_score = min(variance / BLUR_THRESHOLD, 1.0)
    if variance < BLUR_THRESHOLD:
        flags.append("LOW_QUALITY_BLUR")

    # --- Resolution check ---
    resolution_adequate = width >= MIN_DIMENSION and height >= MIN_DIMENSION
    if not resolution_adequate:
        flags.append("LOW_RESOLUTION")

    # --- Rotation heuristic ---
    # Most exam pages are portrait. If width > height significantly,
    # it might be rotated 90 degrees. This is a rough heuristic.
    possibly_rotated = False
    if width > height * 1.3 and height > 200:
        possibly_rotated = True
        flags.append("POSSIBLY_ROTATED")

    # --- Composite score ---
    score = blur_score
    if not resolution_adequate:
        score *= 0.7
    if possibly_rotated:
        score *= 0.8

    score = max(0.0, min(1.0, score))

    return QualityResult(
        score=round(score, 3),
        blur_score=round(blur_score, 3),
        resolution_adequate=resolution_adequate,
        possibly_rotated=possibly_rotated,
        flags=flags,
    )
