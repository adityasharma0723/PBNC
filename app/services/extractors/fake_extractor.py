"""Fake extractor for tests and offline demos.

Returns deterministic results based on page_number and page_text content.
Uses fixture-like logic to simulate various scenarios:
- Page 1-2: questions pages with MCQs
- Page 3: mixed page (questions + answer key)
- Questions at page boundaries get continues_from/continues_on flags
- Answer key entries for matching tests

This enables full pipeline testing without an LLM API key.
"""

from app.services.extractors.base import (
    Extractor,
    ExtractedQuestion,
    ExtractedAnswerKeyEntry,
    PageExtraction,
)


class FakeExtractor:
    """Deterministic extractor for testing.

    Behavior is driven by page_number and keywords in page_text.
    """

    def extract_page(
        self,
        page_image_bytes: bytes,
        page_text: str | None,
        page_number: int,
    ) -> PageExtraction:
        text = page_text or ""
        text_lower = text.lower()

        # Detect answer key pages
        if "answer key" in text_lower or "answer" in text_lower and "key" in text_lower:
            return self._answer_key_page(text, page_number)

        # Detect blank pages
        if len(text.strip()) < 10 and len(page_image_bytes) < 1000:
            return PageExtraction(page_type="blank")

        # Default: generate questions based on page number
        return self._questions_page(text, page_number)

    def _questions_page(self, text: str, page_number: int) -> PageExtraction:
        """Generate fake questions for a page."""
        questions = []
        base_num = (page_number - 1) * 5

        for i in range(1, 6):
            q_num = base_num + i
            continues_on_next = (i == 5 and page_number < 3)  # Last Q on pages 1-2 continues
            continues_from_prev = (i == 1 and page_number > 1)  # First Q on pages 2+ is continuation

            # Skip number for continuations from previous page
            number = None if continues_from_prev else str(q_num)

            q = ExtractedQuestion(
                number=number,
                text=f"What is the capital of Country {q_num}?" if not continues_from_prev
                     else f"...which was established in the year 1900 + {q_num}?",
                options=[
                    {"label": "A", "text": f"City Alpha {q_num}"},
                    {"label": "B", "text": f"City Beta {q_num}"},
                    {"label": "C", "text": f"City Gamma {q_num}"},
                    {"label": "D", "text": f"City Delta {q_num}"},
                ],
                type="mcq_single",
                has_image=(q_num % 7 == 0),
                has_table=(q_num % 11 == 0),
                continues_from_previous=continues_from_prev,
                continues_on_next=continues_on_next,
                model_confidence=0.92 if number else 0.65,
            )
            questions.append(q)

        return PageExtraction(
            page_type="questions",
            orientation_ok=True,
            questions=questions,
        )

    def _answer_key_page(self, text: str, page_number: int) -> PageExtraction:
        """Generate fake answer key entries."""
        answers = ["A", "B", "C", "D", "A", "B", "C", "D", "A", "B"]
        entries = [
            ExtractedAnswerKeyEntry(number=str(i + 1), answer=answers[i])
            for i in range(10)
        ]

        # Add one entry with no matching question (for unmatched testing)
        entries.append(ExtractedAnswerKeyEntry(number="99", answer="C"))

        return PageExtraction(
            page_type="answer_key",
            orientation_ok=True,
            answer_key_entries=entries,
        )
