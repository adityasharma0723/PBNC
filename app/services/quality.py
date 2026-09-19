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

BLUR_THRESHOLD = 100.0
MIN_RESOLUTION = 150
MIN_DIMENSION = 500

@dataclass
class QualityResult:
    score: float
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

    edges = gray.filter(ImageFilter.FIND_EDGES)
    get_pixels = getattr(edges, "get_flattened_data", edges.getdata)
    edge_pixels = list(get_pixels())
    n = len(edge_pixels)
    if n > 0:
        mean = sum(edge_pixels) / n
        variance = sum((p - mean) ** 2 for p in edge_pixels) / n
    else:
        variance = 0.0

    blur_score = min(variance / BLUR_THRESHOLD, 1.0)
    if variance < BLUR_THRESHOLD:
        flags.append("LOW_QUALITY_BLUR")

    resolution_adequate = width >= MIN_DIMENSION and height >= MIN_DIMENSION
    if not resolution_adequate:
        flags.append("LOW_RESOLUTION")

    possibly_rotated = False
    if width > height * 1.3 and height > 200:
        possibly_rotated = True
        flags.append("POSSIBLY_ROTATED")

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
