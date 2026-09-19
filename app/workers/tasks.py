"""Celery tasks: document processing pipeline.

Pipeline steps (each documented inline):
1. Validate & mark processing
2. Render pages (PDF -> images + text; image -> single page)
3. Quality check per page
4. Extract via configured Extractor
5. Stitch cross-page questions
6. Store questions and answer key entries
7. Match answers within group
8. Compute confidence scores
9. Create review items
10. Update document status

Design: tasks are idempotent. Re-running process_document on the same
document will clear previous results and reprocess. The sync session
is used because Celery runs in a sync context.
"""

import os
import traceback
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, delete

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import SyncSessionLocal
from app.models.document import Document, DocumentStatus, DocumentRole
from app.models.page import Page, PageType
from app.models.question import Question, QuestionType, AnswerStatus, QuestionStatus
from app.models.review import ReviewItem, Severity
from app.models.answer_key import AnswerKeyEntry
from app.services.extractors.llm_extractor import get_extractor
from app.services.page_renderer import render_pdf_pages, render_image_page
from app.services.quality import assess_quality
from app.services.stitching import stitch_questions
from app.services.confidence import compute_confidence
from app.services.answer_key import normalize_question_number
from app.services.storage import get_absolute_path
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(bind=True, name="process_document", max_retries=1)
def process_document(self, document_id: str) -> dict:
    """Main document processing pipeline."""
    session = SyncSessionLocal()
    try:
        return _process(session, document_id)
    except Exception as e:
        logger.error(f"Pipeline failed for {document_id}: {e}\n{traceback.format_exc()}")
        _mark_failed(session, document_id, str(e))
        return {"document_id": document_id, "status": "failed"}
    finally:
        session.close()


def _process(session, document_id: str) -> dict:
    """Core pipeline logic."""
    # --- 1. Load and validate ---
    doc_uuid = uuid.UUID(str(document_id)) if not isinstance(document_id, uuid.UUID) else document_id
    doc = session.execute(
        select(Document).where(Document.id == doc_uuid)
    ).scalar_one_or_none()

    if not doc:
        logger.error(f"Document {document_id} not found")
        return {"document_id": document_id, "status": "not_found"}

    doc.status = DocumentStatus.processing
    doc.progress_pct = 5
    doc.updated_at = datetime.now(timezone.utc)
    session.commit()

    # Clear previous results (idempotency)
    session.execute(delete(Page).where(Page.document_id == doc.id))
    session.execute(delete(Question).where(Question.document_id == doc.id))
    session.execute(delete(ReviewItem).where(ReviewItem.document_id == doc.id))
    session.execute(delete(AnswerKeyEntry).where(AnswerKeyEntry.document_id == doc.id))
    session.commit()

    # Read file
    abs_path = get_absolute_path(doc.stored_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Stored file not found: {doc.stored_path}")

    with open(abs_path, "rb") as f:
        file_bytes = f.read()

    # --- 2. Render pages ---
    if doc.mime_type == "application/pdf":
        rendered_pages = render_pdf_pages(file_bytes)
    else:
        rendered_pages = [render_image_page(file_bytes)]

    doc.page_count = len(rendered_pages)
    doc.progress_pct = 20
    session.commit()

    # --- 3-4. Quality check + Extract per page ---
    extractor = get_extractor()
    pages_questions = []
    page_numbers = []
    review_items = []
    has_warnings = False

    for i, rp in enumerate(rendered_pages):
        page_num = rp["page_number"]

        # Quality assessment
        quality = assess_quality(rp["image_bytes"])

        # Create Page record
        page_type_str = "other"
        raw_text = rp.get("raw_text")

        page = Page(
            document_id=doc.id,
            page_number=page_num,
            has_text_layer=rp["has_text_layer"],
            quality_score=quality.score,
            rotation_applied=0,
            page_type=PageType.other,
            image_path=rp["image_path"],
            raw_text=raw_text,
        )

        # Extract content
        try:
            extraction = extractor.extract_page(
                rp["image_bytes"],
                raw_text,
                page_num,
            )
            page_type_str = extraction.page_type
            page.page_type = PageType(page_type_str) if page_type_str in PageType.__members__ else PageType.other

            pages_questions.append(extraction.questions)
            page_numbers.append(page_num)

            # Store answer key entries from this page
            for ake in extraction.answer_key_entries:
                entry = AnswerKeyEntry(
                    document_id=doc.id,
                    question_number=ake.number,
                    answer_value=ake.answer,
                    source_page=page_num,
                    raw_text=f"{ake.number}: {ake.answer}",
                )
                session.add(entry)

            # Check orientation
            if not extraction.orientation_ok:
                review_items.append(_review(
                    doc.id, None, Severity.warning, "POSSIBLY_ROTATED",
                    f"Page {page_num} may be rotated", page_num
                ))
                has_warnings = True

        except Exception as e:
            logger.error(f"Extraction failed for page {page_num}: {e}")
            pages_questions.append([])
            page_numbers.append(page_num)
            review_items.append(_review(
                doc.id, None, Severity.error, "EXTRACTION_FAILED",
                f"Failed to extract page {page_num}: {type(e).__name__}", page_num
            ))
            has_warnings = True

        # Quality review items
        for flag in quality.flags:
            review_items.append(_review(
                doc.id, None, Severity.warning, flag,
                f"Page {page_num}: {flag.replace('_', ' ').lower()}", page_num
            ))
            has_warnings = True

        session.add(page)

        # Update progress
        doc.progress_pct = 20 + int(60 * (i + 1) / len(rendered_pages))
        session.commit()

    # --- 5. Stitch cross-page questions ---
    stitched = stitch_questions(pages_questions, page_numbers)

    # --- 6. Store questions ---
    question_objects = []
    for sq in stitched:
        q_type = sq.get("type", "unknown")
        if q_type not in QuestionType.__members__:
            q_type = "unknown"

        q = Question(
            document_id=doc.id,
            group_id=doc.group_id,
            question_number=sq.get("number"),
            question_text=sq["text"],
            question_type=QuestionType(q_type),
            options=sq.get("options"),
            has_image=sq.get("has_image", False),
            has_table=sq.get("has_table", False),
            source_pages=sq.get("source_pages", []),
            answer=None,
            answer_status=AnswerStatus.not_found,
            confidence=sq.get("model_confidence", 0.5),
            status=QuestionStatus.extracted,
            flags=sq.get("flags", []),
        )
        session.add(q)
        session.flush()  # Get the ID
        question_objects.append(q)

    session.commit()
    doc.progress_pct = 85
    session.commit()

    # --- 7. Answer key matching ---
    _match_answers_for_document(session, doc, question_objects, review_items)
    has_warnings = has_warnings or any(
        r.severity in (Severity.warning, Severity.error) for r in review_items
        if isinstance(r, ReviewItem)
    )

    # --- 8. Confidence scoring ---
    for q in question_objects:
        # Find page quality for this question's source pages
        page_quality = None
        if q.source_pages:
            page_result = session.execute(
                select(Page.quality_score).where(
                    Page.document_id == doc.id,
                    Page.page_number.in_(q.source_pages),
                )
            )
            qualities = [r[0] for r in page_result if r[0] is not None]
            if qualities:
                page_quality = min(qualities)

        conf = compute_confidence(
            model_confidence=q.confidence,
            question_number=q.question_number,
            question_text=q.question_text,
            question_type=q.question_type.value,
            options=q.options,
            has_image=q.has_image,
            has_table=q.has_table,
            existing_flags=q.flags or [],
            answer_status=q.answer_status.value,
            page_quality=page_quality,
        )
        q.confidence = conf.confidence
        q.status = QuestionStatus(conf.status)
        q.flags = conf.flags

        # Create review items for low-confidence questions
        if q.status == QuestionStatus.needs_review:
            review_items.append(_review(
                doc.id, q.id, Severity.warning, "LOW_CONFIDENCE",
                f"Question {q.question_number or '?'}: confidence {conf.confidence:.2f}, "
                f"flags: {', '.join(conf.flags)}",
                q.source_pages[0] if q.source_pages else None,
            ))
            has_warnings = True

    # --- 9. Save review items ---
    for ri in review_items:
        if isinstance(ri, ReviewItem):
            session.add(ri)
        else:
            session.add(ri)

    # --- 10. Final status ---
    doc.progress_pct = 100
    doc.status = (
        DocumentStatus.completed_with_warnings if has_warnings
        else DocumentStatus.completed
    )
    doc.updated_at = datetime.now(timezone.utc)

    # Update document role based on page types
    _infer_document_role(session, doc)

    session.commit()

    logger.info(
        f"Document {document_id} processed: "
        f"{len(question_objects)} questions, "
        f"{len(review_items)} review items, "
        f"status={doc.status.value}"
    )

    return {
        "document_id": document_id,
        "status": doc.status.value,
        "questions": len(question_objects),
        "review_items": len(review_items),
    }


def _match_answers_for_document(session, doc, question_objects, review_items):
    """Match answer key entries to questions for this document and its group."""
    # Collect all answer entries for this document
    entries = session.execute(
        select(AnswerKeyEntry).where(AnswerKeyEntry.document_id == doc.id)
    ).scalars().all()

    # If document is in a group, also get entries from other group documents
    if doc.group_id:
        group_entries = session.execute(
            select(AnswerKeyEntry).where(
                AnswerKeyEntry.document_id.in_(
                    select(Document.id).where(Document.group_id == doc.group_id)
                )
            )
        ).scalars().all()
        entries = list(group_entries)

        # Also get questions from other documents in the group
        group_questions = session.execute(
            select(Question).where(
                Question.group_id == doc.group_id,
                Question.document_id != doc.id,
            )
        ).scalars().all()
        all_questions = list(question_objects) + list(group_questions)
    else:
        all_questions = list(question_objects)

    if not entries:
        return

    # Build index by normalized number
    q_by_number: dict[str, list[Question]] = {}
    for q in all_questions:
        if q.question_number:
            norm = normalize_question_number(q.question_number)
            q_by_number.setdefault(norm, []).append(q)

    # Group answer entries by normalized question number to detect duplicate keys
    entries_by_number: dict[str, list[AnswerKeyEntry]] = {}
    for entry in entries:
        norm = normalize_question_number(entry.question_number)
        entries_by_number.setdefault(norm, []).append(entry)

    for norm, num_entries in entries_by_number.items():
        matching = q_by_number.get(norm, [])

        if len(num_entries) > 1:
            # Duplicate question numbers in the key -> ambiguous, answer null
            for q in matching:
                q.answer = None
                q.answer_status = AnswerStatus.ambiguous
                if "AMBIGUOUS_ANSWER_KEY" not in (q.flags or []):
                    q.flags = (q.flags or []) + ["AMBIGUOUS_ANSWER_KEY"]
            review_items.append(_review(
                doc.id, matching[0].id if matching else None, Severity.warning, "AMBIGUOUS_ANSWER_KEY",
                f"Duplicate answer key entries for question '{norm}': "
                f"{[e.answer_value for e in num_entries]}",
                num_entries[0].source_page,
            ))
            continue

        entry = num_entries[0]

        if len(matching) == 0:
            # Unmatched entry
            review_items.append(_review(
                doc.id, None, Severity.info, "UNMATCHED_ANSWER_KEY",
                f"Answer key entry '{entry.question_number}={entry.answer_value}' "
                f"has no matching question",
                entry.source_page,
            ))
        elif len(matching) == 1:
            q = matching[0]
            entry.matched_question_id = q.id

            # Validate answer label in options
            flags = []
            if q.options:
                option_labels = {
                    opt.get("label", "").upper()
                    for opt in q.options
                    if isinstance(opt, dict)
                }
                if entry.answer_value.upper() not in option_labels:
                    flags.append("ANSWER_NOT_IN_OPTIONS")
                    review_items.append(_review(
                        doc.id, q.id, Severity.warning, "ANSWER_NOT_IN_OPTIONS",
                        f"Answer '{entry.answer_value}' not in options "
                        f"{sorted(option_labels)} for Q{entry.question_number}",
                        entry.source_page,
                    ))

            q.answer = {
                "value": entry.answer_value,
                "source_document_id": str(entry.document_id),
                "source_page": entry.source_page,
                "match_method": "normalized_number",
            }
            q.answer_status = AnswerStatus.matched
            if flags:
                q.flags = (q.flags or []) + flags
        else:
            # Ambiguous: multiple questions with same number
            entry.matched_question_id = matching[0].id
            for q in matching:
                q.answer_status = AnswerStatus.ambiguous
                q.flags = (q.flags or []) + ["AMBIGUOUS_QUESTION_NUMBER"]
            review_items.append(_review(
                doc.id, matching[0].id, Severity.warning, "AMBIGUOUS_ANSWER_MATCH",
                f"Answer key entry '{entry.question_number}' matches "
                f"{len(matching)} questions",
                entry.source_page,
            ))


def _infer_document_role(session, doc):
    """Infer document role from page types."""
    pages = session.execute(
        select(Page.page_type).where(Page.document_id == doc.id)
    ).scalars().all()

    if not pages:
        return

    types_set = set(pages)
    if types_set == {PageType.answer_key}:
        doc.role = DocumentRole.answer_key
    elif types_set == {PageType.questions}:
        doc.role = DocumentRole.question_paper
    elif PageType.answer_key in types_set and PageType.questions in types_set:
        doc.role = DocumentRole.mixed
    elif PageType.mixed in types_set:
        doc.role = DocumentRole.mixed


def _review(doc_id, question_id, severity, code, message, page_number=None):
    """Create a ReviewItem."""
    return ReviewItem(
        document_id=doc_id,
        question_id=question_id,
        severity=severity,
        code=code,
        message=message,
        page_number=page_number,
    )


def _mark_failed(session, document_id, error_msg):
    """Mark a document as failed with a safe error message."""
    try:
        doc_uuid = uuid.UUID(str(document_id)) if not isinstance(document_id, uuid.UUID) else document_id
        doc = session.execute(
            select(Document).where(Document.id == doc_uuid)
        ).scalar_one_or_none()
        if doc:
            doc.status = DocumentStatus.failed
            doc.error_message = error_msg[:500]  # Truncate for safety
            doc.updated_at = datetime.now(timezone.utc)
            session.commit()
    except Exception:
        session.rollback()
