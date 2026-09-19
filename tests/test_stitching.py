"""Tests for cross-page question stitching."""

import pytest
from app.services.stitching import stitch_questions
from app.services.extractors.base import ExtractedQuestion


def _q(number=None, text="Q text", continues_from=False, continues_on=False,
       options=None, confidence=0.9):
    """Helper to create ExtractedQuestion instances."""
    return ExtractedQuestion(
        number=number,
        text=text,
        options=options or [],
        type="mcq_single",
        continues_from_previous=continues_from,
        continues_on_next=continues_on,
        model_confidence=confidence,
    )


class TestStitching:

    def test_no_stitching_needed(self):
        """Normal questions stay separate."""
        pages = [
            [_q("1", "Q1"), _q("2", "Q2")],
            [_q("3", "Q3")],
        ]
        result = stitch_questions(pages, [1, 2])
        assert len(result) == 3
        assert result[0]["number"] == "1"
        assert result[0]["source_pages"] == [1]

    def test_basic_stitching(self):
        """Two-part question across pages merges correctly."""
        pages = [
            [_q("1", "Q1"), _q("2", "Start of Q2", continues_on=True)],
            [_q(None, "end of Q2", continues_from=True), _q("3", "Q3")],
        ]
        result = stitch_questions(pages, [1, 2])
        assert len(result) == 3
        # Stitched question
        assert result[1]["number"] == "2"
        assert "Start of Q2" in result[1]["text"]
        assert "end of Q2" in result[1]["text"]
        assert result[1]["source_pages"] == [1, 2]
        assert "STITCHED_ACROSS_PAGES" in result[1]["flags"]

    def test_stitching_inherits_number(self):
        """Continuation without number inherits from first part."""
        pages = [
            [_q("5", "Start", continues_on=True)],
            [_q(None, "End", continues_from=True)],
        ]
        result = stitch_questions(pages, [1, 2])
        assert len(result) == 1
        assert result[0]["number"] == "5"

    def test_stitching_merges_options(self):
        """Options from both parts are merged."""
        pages = [
            [_q("1", "Q text", continues_on=True,
                options=[{"label": "A", "text": "opt A"}])],
            [_q(None, "continued", continues_from=True,
                options=[{"label": "B", "text": "opt B"}])],
        ]
        result = stitch_questions(pages, [1, 2])
        assert len(result) == 1
        assert len(result[0]["options"]) == 2

    def test_missing_continuation(self):
        """Question flagged continues_on but no continuation follows."""
        pages = [
            [_q("1", "Start", continues_on=True)],
            [_q("2", "Normal Q")],
        ]
        result = stitch_questions(pages, [1, 2])
        assert len(result) == 2
        assert "MISSING_CONTINUATION" in result[0]["flags"]

    def test_three_page_stitch(self):
        """Question spanning three pages."""
        pages = [
            [_q("1", "Part 1", continues_on=True)],
            [_q(None, "Part 2", continues_from=True, continues_on=True)],
            [_q(None, "Part 3", continues_from=True)],
        ]
        result = stitch_questions(pages, [1, 2, 3])
        assert len(result) == 1
        assert "Part 1" in result[0]["text"]
        assert "Part 2" in result[0]["text"]
        assert "Part 3" in result[0]["text"]
        assert result[0]["source_pages"] == [1, 2, 3]

    def test_confidence_takes_minimum(self):
        """Stitched question uses the lower confidence."""
        pages = [
            [_q("1", "Part 1", continues_on=True, confidence=0.95)],
            [_q(None, "Part 2", continues_from=True, confidence=0.60)],
        ]
        result = stitch_questions(pages, [1, 2])
        assert result[0]["model_confidence"] == 0.60

    def test_empty_input(self):
        """No pages returns no questions."""
        assert stitch_questions([], []) == []

    def test_single_page_no_stitching(self):
        """Single page with no continuation flags."""
        pages = [[_q("1", "Q1"), _q("2", "Q2")]]
        result = stitch_questions(pages, [1])
        assert len(result) == 2
