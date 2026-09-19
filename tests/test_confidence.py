"""Tests for confidence scoring."""

import pytest
from app.services.confidence import compute_confidence


class TestConfidenceScoring:

    def test_high_confidence_extracted(self):
        result = compute_confidence(
            model_confidence=0.95,
            question_number="1",
            question_text="What is the capital of France?",
            question_type="mcq_single",
            options=[{"label": "A", "text": "Paris"}, {"label": "B", "text": "London"},
                     {"label": "C", "text": "Berlin"}, {"label": "D", "text": "Madrid"}],
            has_image=False,
            has_table=False,
            existing_flags=[],
            answer_status="matched",
            page_quality=0.9,
        )
        assert result.status == "extracted"
        assert result.confidence >= 0.80

    def test_missing_number_penalty(self):
        result = compute_confidence(
            model_confidence=0.85,
            question_number=None,
            question_text="What is the capital of France?",
            question_type="mcq_single",
            options=[{"label": "A", "text": "Paris"}, {"label": "B", "text": "London"}],
            has_image=False,
            has_table=False,
            existing_flags=[],
            answer_status="not_found",
            page_quality=0.9,
        )
        assert "MISSING_NUMBER" in result.flags
        assert result.confidence < 0.85

    def test_bad_option_count_penalty(self):
        """MCQ with 1 option should be flagged."""
        result = compute_confidence(
            model_confidence=0.90,
            question_number="1",
            question_text="What is 2+2?",
            question_type="mcq_single",
            options=[{"label": "A", "text": "4"}],  # Only 1 option
            has_image=False,
            has_table=False,
            existing_flags=[],
            answer_status="not_found",
            page_quality=0.9,
        )
        assert "BAD_OPTION_COUNT" in result.flags

    def test_short_text_penalty(self):
        result = compute_confidence(
            model_confidence=0.90,
            question_number="1",
            question_text="Q?",  # Very short
            question_type="unknown",
            options=None,
            has_image=False,
            has_table=False,
            existing_flags=[],
            answer_status="not_found",
            page_quality=0.9,
        )
        assert "SHORT_TEXT" in result.flags

    def test_low_quality_page_penalty(self):
        result = compute_confidence(
            model_confidence=0.90,
            question_number="1",
            question_text="What is the capital?",
            question_type="mcq_single",
            options=[{"label": "A", "text": "Paris"}, {"label": "B", "text": "London"}],
            has_image=False,
            has_table=False,
            existing_flags=[],
            answer_status="matched",
            page_quality=0.3,  # Low quality
        )
        assert "LOW_QUALITY_BLUR" in result.flags
        assert result.confidence < 0.90

    def test_answer_not_in_options_forces_review(self):
        result = compute_confidence(
            model_confidence=0.95,
            question_number="1",
            question_text="What is the capital of France?",
            question_type="mcq_single",
            options=[{"label": "A", "text": "Paris"}],
            has_image=False,
            has_table=False,
            existing_flags=["ANSWER_NOT_IN_OPTIONS"],
            answer_status="matched",
            page_quality=0.9,
        )
        assert result.status == "needs_review"

    def test_stitched_penalty(self):
        result = compute_confidence(
            model_confidence=0.90,
            question_number="1",
            question_text="This question spans pages",
            question_type="mcq_single",
            options=[{"label": "A", "text": "opt"}, {"label": "B", "text": "opt"}],
            has_image=False,
            has_table=False,
            existing_flags=["STITCHED_ACROSS_PAGES"],
            answer_status="matched",
            page_quality=0.9,
        )
        assert "STITCHED_ACROSS_PAGES" in result.flags
        assert result.confidence < 0.90

    def test_cumulative_penalties(self):
        """Multiple penalties stack and can push to needs_review."""
        result = compute_confidence(
            model_confidence=0.70,
            question_number=None,
            question_text="Q?",
            question_type="mcq_single",
            options=[{"label": "A", "text": "o"}],
            has_image=True,
            has_table=True,
            existing_flags=["STITCHED_ACROSS_PAGES"],
            answer_status="ambiguous",
            page_quality=0.3,
        )
        assert result.status == "needs_review"
        assert result.confidence < 0.50

    def test_thresholds_configurable(self):
        """Verify threshold mapping works correctly."""
        from app.core.config import settings

        # Just above high threshold
        result = compute_confidence(
            model_confidence=settings.CONFIDENCE_HIGH + 0.01,
            question_number="1",
            question_text="Normal question text here",
            question_type="mcq_single",
            options=[{"label": "A", "text": "opt"}, {"label": "B", "text": "opt"}],
            has_image=False,
            has_table=False,
            existing_flags=[],
            answer_status="matched",
            page_quality=0.9,
        )
        assert result.status == "extracted"
