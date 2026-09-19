"""Confidence scoring: transparent, rule-based formula.

Starting from the model's self-reported confidence, applies penalties
for various quality signals. The final score maps to a status:
  >= CONFIDENCE_HIGH (0.80): extracted
  >= CONFIDENCE_LOW  (0.50): partial
  <  CONFIDENCE_LOW:          needs_review

The formula and weights are documented in ARCHITECTURE.md so every
score is explainable. The flags list records which penalties applied.

Weight rationale:
- MISSING_NUMBER (-0.10): common in real exams, moderate concern
- BAD_OPTION_COUNT (-0.10): MCQ with <2 or >6 options is suspect
- SHORT_TEXT (-0.08): very short questions are likely truncated
- STITCHED (-0.05): cross-page stitching adds minor uncertainty
- LOW_QUALITY (-0.10): blurry/low-res pages hurt accuracy
- ANSWER_UNMATCHED (-0.05): no answer found, but question might be OK
- ANSWER_AMBIGUOUS (-0.15): ambiguous matching is a bigger concern
- ANSWER_NOT_IN_OPTIONS (-0.20): likely wrong answer, significant penalty
- HAS_IMAGE (-0.03): images not fully captured
- HAS_TABLE (-0.05): tables not parsed
"""

from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Penalty weights (negative values subtracted from confidence)
PENALTIES = {
    "MISSING_NUMBER": 0.10,
    "BAD_OPTION_COUNT": 0.10,
    "SHORT_TEXT": 0.08,
    "STITCHED_ACROSS_PAGES": 0.05,
    "MISSING_CONTINUATION": 0.12,
    "LOW_QUALITY_BLUR": 0.10,
    "LOW_RESOLUTION": 0.08,
    "POSSIBLY_ROTATED": 0.10,
    "ANSWER_UNMATCHED": 0.05,
    "ANSWER_AMBIGUOUS": 0.15,
    "ANSWER_NOT_IN_OPTIONS": 0.20,
    "HAS_UNCAPTURED_IMAGE": 0.03,
    "HAS_UNCAPTURED_TABLE": 0.05,
    "FAILED_EXTRACTION": 0.50,
}


@dataclass
class ConfidenceResult:
    confidence: float
    status: str  # extracted | partial | needs_review
    flags: list[str]


def compute_confidence(
    model_confidence: float,
    question_number: str | None,
    question_text: str,
    question_type: str,
    options: list[dict] | None,
    has_image: bool,
    has_table: bool,
    existing_flags: list[str],
    answer_status: str,
    page_quality: float | None,
) -> ConfidenceResult:
    """Compute confidence score for a question.

    Returns the final score, status, and accumulated flags.
    Each flag explains a penalty that was applied.
    """
    score = model_confidence
    flags = list(existing_flags)  # Copy to avoid mutating input

    # --- Missing question number ---
    if not question_number:
        _apply_penalty(flags, "MISSING_NUMBER")

    # --- Option count check for MCQ types ---
    if question_type in ("mcq_single", "mcq_multiple"):
        opt_count = len(options) if options else 0
        if opt_count < 2 or opt_count > 6:
            _apply_penalty(flags, "BAD_OPTION_COUNT")

    # --- Very short text ---
    if len(question_text.strip()) < 15:
        _apply_penalty(flags, "SHORT_TEXT")

    # --- Image/table not fully captured ---
    if has_image:
        _apply_penalty(flags, "HAS_UNCAPTURED_IMAGE")
    if has_table:
        _apply_penalty(flags, "HAS_UNCAPTURED_TABLE")

    # --- Answer status penalties ---
    if answer_status == "ambiguous":
        _apply_penalty(flags, "ANSWER_AMBIGUOUS")
    elif answer_status == "unmatched":
        _apply_penalty(flags, "ANSWER_UNMATCHED")

    # --- Page quality ---
    if page_quality is not None and page_quality < 0.5:
        if "LOW_QUALITY_BLUR" not in flags:
            _apply_penalty(flags, "LOW_QUALITY_BLUR")

    # --- Calculate final score ---
    total_penalty = sum(PENALTIES.get(f, 0) for f in flags)
    score = max(0.0, min(1.0, score - total_penalty))

    # --- Map to status ---
    if score >= settings.CONFIDENCE_HIGH:
        status = "extracted"
    elif score >= settings.CONFIDENCE_LOW:
        status = "partial"
    else:
        status = "needs_review"

    # Any error-level flag forces needs_review
    error_flags = {"FAILED_EXTRACTION", "ANSWER_NOT_IN_OPTIONS", "MISSING_CONTINUATION"}
    if error_flags & set(flags):
        status = "needs_review"

    return ConfidenceResult(
        confidence=round(score, 3),
        status=status,
        flags=flags,
    )


def _apply_penalty(flags: list[str], flag: str) -> None:
    """Add a flag if not already present."""
    if flag not in flags:
        flags.append(flag)
