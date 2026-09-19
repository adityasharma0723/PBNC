"""Answer key parsing and matching.

Handles answer key entries extracted by the LLM and matches them to
questions by normalized question number within a document group.

Supported formats (examples):
  "1-A", "1. B", "Q1: C", "1 (b)", "1) A", "(1) A", tabular "1 A"

Matching logic:
- Normalize question numbers: strip "Q", "q", "(", ")", ".", leading zeros
- Match across the entire group (question paper + answer key can be
  separate documents uploaded in any order)
- Statuses: matched / unmatched / ambiguous / not_found
- Validates the answer label exists in the question's options

Re-matching is triggered when:
- An answer key document finishes processing
- A document is added to a group
- POST /groups/{id}/rematch is called
"""

import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def normalize_question_number(raw: str) -> str:
    """Normalize a question number for matching.

    Strips prefixes (Q, q), delimiters ((, ), .), and leading zeros.
    Examples: "Q1" -> "1", "(2)" -> "2", "03" -> "3", "Q.5" -> "5",
              "1a" -> "1a" (preserved for sub-questions)
    """
    s = raw.strip()
    # Remove Q/q prefix
    s = re.sub(r'^[Qq]\.?\s*', '', s)
    # Remove surrounding parentheses
    s = re.sub(r'^\((.+)\)$', r'\1', s)
    # Remove trailing ) or .
    s = re.sub(r'[).]$', '', s)
    # Strip leading zeros (but keep "0" itself)
    s = re.sub(r'^0+(\d)', r'\1', s)
    return s.strip()


def parse_answer_key_text(text: str) -> list[dict[str, str]]:
    """Parse free-text answer key into (number, answer) pairs.

    Supports multiple formats:
    - "1-A" or "1 - A"
    - "1. B" or "1.B"
    - "Q1: C" or "Q1 : C"
    - "1) A"
    - "(1) A"
    - "1 A" (space-separated, tabular)
    - "1 (b)" (answer in parens)
    """
    entries = []
    # Pattern matches: optional Q prefix, number, separator, answer
    pattern = re.compile(
        r'(?:^|\n)\s*'
        r'(?:[Qq]\.?\s*)?'         # Optional Q/q prefix
        r'(\d+[a-z]?)'            # Question number (with optional sub-part)
        r'\s*'
        r'[-:.)\]}\s]+'           # Separator(s)
        r'\(?([A-Da-d])\)?'       # Answer (A-D, optionally in parens)
        r'\s*(?:$|\n|,|;)',
        re.MULTILINE,
    )

    for match in pattern.finditer(text):
        number = normalize_question_number(match.group(1))
        answer = match.group(2).upper()
        entries.append({"number": number, "answer": answer})

    return entries


def match_answers(
    questions: list[dict[str, Any]],
    answer_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match answer key entries to questions by normalized number.

    Args:
        questions: list of question dicts with 'question_number' and 'options'
        answer_entries: list of dicts with 'question_number' and 'answer_value'

    Returns:
        list of match result dicts with status and details

    Statuses:
        matched: exactly one question matched, answer label valid
        ambiguous: multiple questions with the same normalized number
        unmatched: answer entry with no matching question
        not_found: question with no matching answer entry
    """
    # Build question index by normalized number
    q_index: dict[str, list[dict]] = {}
    for q in questions:
        if q.get("question_number"):
            norm = normalize_question_number(q["question_number"])
            q_index.setdefault(norm, []).append(q)

    # Group answer entries by normalized question number to detect duplicates
    entries_by_num: dict[str, list[dict]] = {}
    for entry in answer_entries:
        norm_num = normalize_question_number(entry["question_number"])
        entries_by_num.setdefault(norm_num, []).append(entry)

    results = []
    matched_q_ids = set()

    for norm_num, num_entries in entries_by_num.items():
        matching_qs = q_index.get(norm_num, [])

        if len(num_entries) > 1:
            # Duplicate question numbers in the key -> ambiguous, answer null
            for q in matching_qs:
                matched_q_ids.add(id(q))
            results.append({
                "entry": None,
                "status": "ambiguous",
                "question": matching_qs[0] if matching_qs else None,
                "flags": ["AMBIGUOUS_ANSWER_KEY"],
            })
            continue

        entry = num_entries[0]
        answer_val = entry["answer_value"].upper().strip()

        if len(matching_qs) == 0:
            results.append({
                "entry": entry,
                "status": "unmatched",
                "question": None,
                "flags": [],
            })
        elif len(matching_qs) == 1:
            q = matching_qs[0]
            flags = []

            # Validate answer label exists in options
            if q.get("options"):
                option_labels = {
                    opt.get("label", "").upper()
                    for opt in q["options"]
                    if isinstance(opt, dict)
                }
                if answer_val not in option_labels:
                    flags.append("ANSWER_NOT_IN_OPTIONS")

            matched_q_ids.add(id(q))
            results.append({
                "entry": entry,
                "status": "matched",
                "question": q,
                "flags": flags,
            })
        else:
            # Multiple questions with the same number -> ambiguous
            for q in matching_qs:
                matched_q_ids.add(id(q))
            results.append({
                "entry": entry,
                "status": "ambiguous",
                "question": matching_qs[0],
                "flags": ["AMBIGUOUS_QUESTION_NUMBER"],
            })

    # Mark questions with no answer entry
    for q in questions:
        if id(q) not in matched_q_ids:
            results.append({
                "entry": None,
                "status": "not_found",
                "question": q,
                "flags": [],
            })

    return results
