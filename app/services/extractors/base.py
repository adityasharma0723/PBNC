"""Extractor protocol and shared data types.

Defines the contract that all extractors must implement.
Uses a Protocol (structural subtyping) so implementations don't need
to inherit from a base class.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class ExtractedQuestion(BaseModel):
    """A single question extracted from a page."""
    number: str | None = Field(None, description="Question number as it appears, or null")
    text: str
    options: list[dict] = Field(default_factory=list, description='[{"label":"A","text":"..."}]')
    type: str = "unknown"
    has_image: bool = False
    has_table: bool = False
    continues_from_previous: bool = False
    continues_on_next: bool = False
    model_confidence: float = Field(0.5, ge=0.0, le=1.0)


class ExtractedAnswerKeyEntry(BaseModel):
    """A single answer key entry extracted from a page."""
    number: str
    answer: str


class PageExtraction(BaseModel):
    """Complete extraction result for one page."""
    page_type: str = "other"  # questions | answer_key | mixed | blank | other
    orientation_ok: bool = True
    questions: list[ExtractedQuestion] = Field(default_factory=list)
    answer_key_entries: list[ExtractedAnswerKeyEntry] = Field(default_factory=list)


class Extractor(Protocol):
    """Protocol for page content extraction.

    Implementations: LLMExtractor (production), FakeExtractor (tests/demos).
    Selected by env var EXTRACTOR=llm|fake.
    """

    def extract_page(
        self,
        page_image_bytes: bytes,
        page_text: str | None,
        page_number: int,
    ) -> PageExtraction:
        """Extract questions and answer key entries from a single page."""
        ...
