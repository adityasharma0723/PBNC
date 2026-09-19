"""Cross-page question stitching.

When a question spans a page boundary, the extractor flags:
- Page N, last question: continues_on_next=True
- Page N+1, first question: continues_from_previous=True

This module merges them deterministically:
1. Concatenate text (with a space)
2. Merge options (append latter's options to former's)
3. Union source_pages
4. Take the question number from the first part (it has the number)
5. Flag STITCHED_ACROSS_PAGES

Edge cases handled:
- Continuation without a number: inherits from the previous part
- Multiple consecutive continuations: chain them
"""

from app.services.extractors.base import ExtractedQuestion
from app.core.logging import get_logger

logger = get_logger(__name__)


def stitch_questions(
    pages_questions: list[list[ExtractedQuestion]],
    page_numbers: list[int],
) -> list[dict]:
    """Merge questions that span page boundaries.

    Args:
        pages_questions: questions extracted per page, ordered by page number
        page_numbers: corresponding page numbers for each list

    Returns:
        list of merged question dicts with source_pages and flags
    """
    if not pages_questions:
        return []

    result: list[dict] = []
    pending: dict | None = None  # Question being built across pages

    for page_idx, (questions, page_num) in enumerate(zip(pages_questions, page_numbers)):
        for q_idx, q in enumerate(questions):
            q_dict = {
                "number": q.number,
                "text": q.text,
                "options": q.options,
                "type": q.type,
                "has_image": q.has_image,
                "has_table": q.has_table,
                "model_confidence": q.model_confidence,
                "source_pages": [page_num],
                "flags": [],
            }

            if q.continues_from_previous and pending is not None:
                # Merge into pending question
                pending["text"] = pending["text"].rstrip() + " " + q_dict["text"].lstrip()
                pending["options"] = (pending.get("options") or []) + (q_dict.get("options") or [])
                pending["source_pages"] = sorted(set(pending["source_pages"] + q_dict["source_pages"]))
                pending["has_image"] = pending["has_image"] or q_dict["has_image"]
                pending["has_table"] = pending["has_table"] or q_dict["has_table"]
                # Use lower confidence of the parts
                pending["model_confidence"] = min(
                    pending["model_confidence"], q_dict["model_confidence"]
                )
                if "STITCHED_ACROSS_PAGES" not in pending["flags"]:
                    pending["flags"].append("STITCHED_ACROSS_PAGES")

                if not q.continues_on_next:
                    # This continuation is complete
                    result.append(pending)
                    pending = None
                # else: continues further, keep building
            elif q.continues_from_previous and pending is None:
                # Orphan continuation (no preceding question flagged continues_on_next)
                q_dict["flags"].append("ORPHAN_CONTINUATION")
                if q.continues_on_next:
                    pending = q_dict
                else:
                    result.append(q_dict)
            elif q.continues_on_next:
                # Start of a cross-page question
                if pending is not None:
                    # Previous pending never got its continuation; emit as-is
                    if "MISSING_CONTINUATION" not in pending["flags"]:
                        pending["flags"].append("MISSING_CONTINUATION")
                    result.append(pending)
                pending = q_dict
            else:
                # Normal question, not spanning pages
                if pending is not None:
                    # Previous pending never got its continuation; emit as-is
                    if "MISSING_CONTINUATION" not in pending["flags"]:
                        pending["flags"].append("MISSING_CONTINUATION")
                    result.append(pending)
                    pending = None
                result.append(q_dict)

    # Flush any remaining pending question
    if pending is not None:
        if "MISSING_CONTINUATION" not in pending["flags"]:
            pending["flags"].append("MISSING_CONTINUATION")
        result.append(pending)

    return result
