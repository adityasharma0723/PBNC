"""Tests for answer key parsing and matching."""

import pytest
from app.services.answer_key import normalize_question_number, parse_answer_key_text, match_answers

class TestNormalizeQuestionNumber:

    def test_plain_number(self):
        assert normalize_question_number("1") == "1"

    def test_q_prefix(self):
        assert normalize_question_number("Q1") == "1"

    def test_q_dot_prefix(self):
        assert normalize_question_number("Q.1") == "1"

    def test_parenthesized(self):
        assert normalize_question_number("(1)") == "1"

    def test_trailing_paren(self):
        assert normalize_question_number("1)") == "1"

    def test_trailing_dot(self):
        assert normalize_question_number("1.") == "1"

    def test_leading_zeros(self):
        assert normalize_question_number("03") == "3"

    def test_sub_question(self):
        assert normalize_question_number("1a") == "1a"

    def test_lowercase_q(self):
        assert normalize_question_number("q5") == "5"

    def test_whitespace(self):
        assert normalize_question_number("  Q.3  ") == "3"

class TestParseAnswerKeyText:

    def test_dash_format(self):
        text = "1-A\n2-B\n3-C"
        entries = parse_answer_key_text(text)
        assert len(entries) == 3
        assert entries[0] == {"number": "1", "answer": "A"}
        assert entries[2] == {"number": "3", "answer": "C"}

    def test_dot_format(self):
        text = "1. A\n2. B\n3. C"
        entries = parse_answer_key_text(text)
        assert len(entries) == 3

    def test_q_prefix_colon_format(self):
        text = "Q1: A\nQ2: B\nQ3: C"
        entries = parse_answer_key_text(text)
        assert len(entries) == 3
        assert entries[0]["number"] == "1"

    def test_paren_format(self):
        text = "1) A\n2) B\n3) C"
        entries = parse_answer_key_text(text)
        assert len(entries) == 3

    def test_answer_in_parens(self):
        text = "1 (b)\n2 (a)\n3 (c)"
        entries = parse_answer_key_text(text)
        assert len(entries) == 3
        assert entries[0]["answer"] == "B"

    def test_mixed_format(self):
        text = "1-A\n2. B\nQ3: C\n4) D"
        entries = parse_answer_key_text(text)
        assert len(entries) == 4

class TestMatchAnswers:

    def _make_questions(self, numbers):
        return [
            {
                "question_number": n,
                "options": [
                    {"label": "A", "text": "opt A"},
                    {"label": "B", "text": "opt B"},
                    {"label": "C", "text": "opt C"},
                    {"label": "D", "text": "opt D"},
                ],
            }
            for n in numbers
        ]

    def _make_entries(self, pairs):
        return [
            {"question_number": n, "answer_value": a}
            for n, a in pairs
        ]

    def test_basic_matching(self):
        questions = self._make_questions(["1", "2", "3"])
        entries = self._make_entries([("1", "A"), ("2", "B"), ("3", "C")])
        results = match_answers(questions, entries)

        matched = [r for r in results if r["status"] == "matched"]
        assert len(matched) == 3

    def test_unmatched_entry(self):
        """Answer entry with no matching question."""
        questions = self._make_questions(["1", "2"])
        entries = self._make_entries([("1", "A"), ("99", "C")])
        results = match_answers(questions, entries)

        unmatched = [r for r in results if r["status"] == "unmatched"]
        assert len(unmatched) == 1
        assert unmatched[0]["entry"]["question_number"] == "99"

    def test_not_found(self):
        """Question with no answer entry."""
        questions = self._make_questions(["1", "2", "3"])
        entries = self._make_entries([("1", "A")])
        results = match_answers(questions, entries)

        not_found = [r for r in results if r["status"] == "not_found"]
        assert len(not_found) == 2

    def test_ambiguous_matching(self):
        """Multiple questions with the same normalized number."""
        questions = self._make_questions(["1", "1"])
        entries = self._make_entries([("1", "A")])
        results = match_answers(questions, entries)

        ambiguous = [r for r in results if r["status"] == "ambiguous"]
        assert len(ambiguous) == 1

    def test_answer_not_in_options(self):
        """Answer label doesn't exist in question options."""
        questions = [{"question_number": "1", "options": [{"label": "A", "text": "opt A"}]}]
        entries = [{"question_number": "1", "answer_value": "D"}]
        results = match_answers(questions, entries)

        matched = [r for r in results if r["status"] == "matched"]
        assert len(matched) == 1
        assert "ANSWER_NOT_IN_OPTIONS" in matched[0]["flags"]

    def test_normalized_matching(self):
        """Q1 in entries matches '1' in questions."""
        questions = self._make_questions(["1", "2"])
        entries = self._make_entries([("Q1", "A"), ("Q.2", "B")])
        results = match_answers(questions, entries)

        matched = [r for r in results if r["status"] == "matched"]
        assert len(matched) == 2

    def test_answer_key_before_questions(self):
        """Answer entries work regardless of which document comes first."""
        questions = self._make_questions(["1", "2", "3"])
        entries = self._make_entries([("1", "A"), ("2", "B"), ("3", "C")])

        results_forward = match_answers(questions, entries)
        results_reverse = match_answers(questions, list(reversed(entries)))

        matched_f = [r for r in results_forward if r["status"] == "matched"]
        matched_r = [r for r in results_reverse if r["status"] == "matched"]
        assert len(matched_f) == len(matched_r) == 3
