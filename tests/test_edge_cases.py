"""Tests for specific edge cases requested by the user:

1. Question split across 3 pages (not just 2).
2. Continuation with no question number.
3. Answer key uploaded BEFORE the question paper in a separate document.
4. Duplicate question numbers in the key -> ambiguous, answer null.
5. Answer label "E" on a 4-option question -> ANSWER_NOT_IN_OPTIONS, confidence lowered.
6. Key entry for Q99 when no Q99 exists -> review item.
"""

import os
import uuid
import pytest
from sqlalchemy import select

from app.db.base import Base
from app.db.session import sync_engine, SyncSessionLocal
from app.models.user import User
from app.models.document import Document, DocumentRole, DocumentStatus
from app.models.group import DocumentGroup
from app.models.page import Page
from app.models.question import Question, QuestionType, AnswerStatus, QuestionStatus
from app.models.review import ReviewItem
from app.models.answer_key import AnswerKeyEntry
from app.services.extractors.base import ExtractedQuestion
from app.services.stitching import stitch_questions
from app.services.answer_key import match_answers
from app.services.confidence import compute_confidence
from app.services.file_validation import validate_file
from app.services.storage import store_file, get_extension_for_mime
from app.workers.tasks import process_document
from app.core.security import hash_password


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=sync_engine)
    yield
    Base.metadata.drop_all(bind=sync_engine)


class TestEdgeCase1SplitAcross3Pages:
    """1. Question split across 3 pages (not just 2)."""

    def test_three_page_stitching(self):
        page1_q = ExtractedQuestion(
            number="1",
            text="In the year 1900, a scientist conducted an experiment",
            options=[{"label": "A", "text": "Option A on page 1"}],
            type="mcq_single",
            continues_from_previous=False,
            continues_on_next=True,
            model_confidence=0.95,
        )
        page2_q = ExtractedQuestion(
            number=None,
            text="observing the reaction of chemical X under heat,",
            options=[{"label": "B", "text": "Option B on page 2"}],
            type="mcq_single",
            continues_from_previous=True,
            continues_on_next=True,
            model_confidence=0.90,
        )
        page3_q = ExtractedQuestion(
            number=None,
            text="which led to what major discovery?",
            options=[
                {"label": "C", "text": "Option C on page 3"},
                {"label": "D", "text": "Option D on page 3"},
            ],
            type="mcq_single",
            continues_from_previous=True,
            continues_on_next=False,
            model_confidence=0.88,
        )

        pages_questions = [[page1_q], [page2_q], [page3_q]]
        result = stitch_questions(pages_questions, [1, 2, 3])

        assert len(result) == 1
        q = result[0]
        assert q["number"] == "1"
        # Full text concatenated in order
        assert "In the year 1900" in q["text"]
        assert "observing the reaction" in q["text"]
        assert "which led to what major discovery?" in q["text"]
        # Options merged from all 3 pages (A, B, C, D)
        assert len(q["options"]) == 4
        labels = [opt["label"] for opt in q["options"]]
        assert labels == ["A", "B", "C", "D"]
        # Source pages unioned
        assert q["source_pages"] == [1, 2, 3]
        # Flagged as stitched without duplicate flags
        assert q["flags"].count("STITCHED_ACROSS_PAGES") == 1
        assert "MISSING_CONTINUATION" not in q["flags"]
        # Model confidence takes the minimum of all 3 parts
        assert q["model_confidence"] == 0.88


class TestEdgeCase2ContinuationNoQuestionNumber:
    """2. Continuation with no question number."""

    def test_continuation_inherits_number_from_previous_page(self):
        page1 = [
            ExtractedQuestion(
                number="42",
                text="The speed of light in a vacuum is approximately",
                options=[{"label": "A", "text": "3x10^8 m/s"}],
                type="mcq_single",
                continues_from_previous=False,
                continues_on_next=True,
                model_confidence=0.95,
            )
        ]
        page2 = [
            ExtractedQuestion(
                number=None,  # No question number on the continuation part
                text="which corresponds to which fundamental constant?",
                options=[{"label": "B", "text": "c"}],
                type="mcq_single",
                continues_from_previous=True,
                continues_on_next=False,
                model_confidence=0.91,
            )
        ]
        result = stitch_questions([page1, page2], [1, 2])

        assert len(result) == 1
        assert result[0]["number"] == "42"  # Successfully inherited
        assert result[0]["source_pages"] == [1, 2]
        assert "STITCHED_ACROSS_PAGES" in result[0]["flags"]

    def test_orphan_continuation_flagged(self):
        """Page 2 claims continuation with no number, but page 1 did not continue."""
        page1 = [
            ExtractedQuestion(
                number="1",
                text="Complete question on page 1",
                options=[],
                type="mcq_single",
                continues_from_previous=False,
                continues_on_next=False,
            )
        ]
        page2 = [
            ExtractedQuestion(
                number=None,  # Orphan continuation without a number
                text="...dangling text from nowhere",
                options=[],
                type="mcq_single",
                continues_from_previous=True,
                continues_on_next=False,
            )
        ]
        result = stitch_questions([page1, page2], [1, 2])
        assert len(result) == 2
        orphan = result[1]
        assert orphan["number"] is None
        assert "ORPHAN_CONTINUATION" in orphan["flags"]


class TestEdgeCase3AnswerKeyUploadedBeforeQuestions:
    """3. Answer key uploaded BEFORE the question paper in a separate document."""

    def test_key_before_questions_pipeline(self, tmp_path):
        """Pipeline integration: answer key processed first, question paper processed second in same group."""
        session = SyncSessionLocal()

        # Create user & group
        user = User(
            id=uuid.uuid4(),
            email=f"edge3_{uuid.uuid4().hex[:6]}@example.com",
            password_hash=hash_password("pw123"),
        )
        group = DocumentGroup(id=uuid.uuid4(), owner_id=user.id, name="Test Group")
        session.add_all([user, group])
        session.commit()

        # 1. Document 1: Answer Key (processed FIRST)
        key_sample_path = os.path.abspath("samples/05_answer_key_separate.pdf")
        with open(key_sample_path, "rb") as f:
            key_bytes = f.read()

        val_key = validate_file(key_bytes)
        ext_key = get_extension_for_mime(val_key.mime_type)
        stored_key, sha_key = store_file(key_bytes, ext_key)

        doc_key = Document(
            id=uuid.uuid4(),
            owner_id=user.id,
            group_id=group.id,
            role=DocumentRole.answer_key,
            original_filename="05_answer_key_separate.pdf",
            stored_path=stored_key,
            mime_type=val_key.mime_type,
            sha256=sha_key,
            size_bytes=val_key.size_bytes,
            page_count=val_key.page_count,
            status=DocumentStatus.queued,
        )
        session.add(doc_key)
        session.commit()

        # Process Answer Key first
        res_key = process_document(str(doc_key.id))
        assert res_key["status"] in ("completed", "completed_with_warnings")

        # Verify answer key entries are in DB
        entries = session.execute(
            select(AnswerKeyEntry).where(AnswerKeyEntry.document_id == doc_key.id)
        ).scalars().all()
        assert len(entries) > 0

        # 2. Document 2: Question Paper (processed SECOND)
        qp_sample_path = os.path.abspath("samples/04_cross_page.pdf")
        with open(qp_sample_path, "rb") as f:
            qp_bytes = f.read()

        val_qp = validate_file(qp_bytes)
        ext_qp = get_extension_for_mime(val_qp.mime_type)
        stored_qp, sha_qp = store_file(qp_bytes, ext_qp)

        doc_qp = Document(
            id=uuid.uuid4(),
            owner_id=user.id,
            group_id=group.id,
            role=DocumentRole.question_paper,
            original_filename="04_cross_page.pdf",
            stored_path=stored_qp,
            mime_type=val_qp.mime_type,
            sha256=sha_qp,
            size_bytes=val_qp.size_bytes,
            page_count=val_qp.page_count,
            status=DocumentStatus.queued,
        )
        session.add(doc_qp)
        session.commit()

        # Process Question Paper second
        res_qp = process_document(str(doc_qp.id))
        assert res_qp["status"] in ("completed", "completed_with_warnings")

        # 3. Verify Question Paper questions successfully matched with Answer Key from Document 1
        qp_questions = session.execute(
            select(Question).where(Question.document_id == doc_qp.id)
        ).scalars().all()
        assert len(qp_questions) > 0

        matched_questions = [q for q in qp_questions if q.answer_status == AnswerStatus.matched]
        assert len(matched_questions) > 0
        # Check that answer is present on matched questions
        assert matched_questions[0].answer is not None
        assert "value" in matched_questions[0].answer
        session.close()


class TestEdgeCase4DuplicateQuestionNumbersInKey:
    """4. Duplicate question numbers in the key -> ambiguous, answer null."""

    def test_duplicate_key_entries_in_match_answers(self):
        questions = [
            {
                "question_number": "1",
                "options": [
                    {"label": "A", "text": "opt A"},
                    {"label": "B", "text": "opt B"},
                ],
            }
        ]
        # Duplicate key entries for Q1: "1-A" and "1-B"
        duplicate_entries = [
            {"question_number": "1", "answer_value": "A"},
            {"question_number": "1", "answer_value": "B"},
        ]
        results = match_answers(questions, duplicate_entries)

        # Must report ambiguous, with AMBIGUOUS_ANSWER_KEY flag
        ambiguous = [r for r in results if r["status"] == "ambiguous"]
        assert len(ambiguous) == 1
        assert "AMBIGUOUS_ANSWER_KEY" in ambiguous[0]["flags"]

    def test_duplicate_key_entries_in_pipeline(self):
        """In pipeline: duplicate entries set answer=None and answer_status=ambiguous."""
        session = SyncSessionLocal()

        user = User(
            id=uuid.uuid4(),
            email=f"edge4_{uuid.uuid4().hex[:6]}@example.com",
            password_hash=hash_password("pw123"),
        )
        doc = Document(
            id=uuid.uuid4(),
            owner_id=user.id,
            role=DocumentRole.question_paper,
            original_filename="dummy.pdf",
            stored_path="dummy.pdf",
            mime_type="application/pdf",
            sha256="0" * 64,
            size_bytes=100,
            page_count=1,
            status=DocumentStatus.queued,
        )
        session.add_all([user, doc])
        session.commit()

        # Add a question
        q1 = Question(
            id=uuid.uuid4(),
            document_id=doc.id,
            question_number="1",
            question_text="What is 1 + 1?",
            question_type=QuestionType.mcq_single,
            options=[{"label": "A", "text": "2"}, {"label": "B", "text": "3"}],
            confidence=0.90,
            status=QuestionStatus.extracted,
        )
        # Add duplicate answer key entries for Q1
        entry1 = AnswerKeyEntry(
            id=uuid.uuid4(),
            document_id=doc.id,
            question_number="1",
            answer_value="A",
            source_page=1,
            raw_text="1: A",
        )
        entry2 = AnswerKeyEntry(
            id=uuid.uuid4(),
            document_id=doc.id,
            question_number="1",
            answer_value="B",
            source_page=1,
            raw_text="1: B",
        )
        session.add_all([q1, entry1, entry2])
        session.commit()

        from app.workers.tasks import _match_answers_for_document
        review_items = []
        _match_answers_for_document(session, doc, [q1], review_items)

        # Assert: answer is null, status is ambiguous
        assert q1.answer is None
        assert q1.answer_status == AnswerStatus.ambiguous
        assert "AMBIGUOUS_ANSWER_KEY" in q1.flags

        # Assert: review item generated
        assert any(r.code == "AMBIGUOUS_ANSWER_KEY" for r in review_items)
        session.close()


class TestEdgeCase5AnswerLabelNotInOptions:
    """5. Answer label 'E' on a 4-option question -> ANSWER_NOT_IN_OPTIONS, confidence lowered."""

    def test_answer_not_in_options_flag_and_confidence(self):
        # 4 options: A, B, C, D
        options = [
            {"label": "A", "text": "Alpha"},
            {"label": "B", "text": "Beta"},
            {"label": "C", "text": "Gamma"},
            {"label": "D", "text": "Delta"},
        ]
        questions = [{"question_number": "1", "options": options}]
        # Answer key specifies "E"
        entries = [{"question_number": "1", "answer_value": "E"}]

        results = match_answers(questions, entries)
        assert len(results) == 1
        assert "ANSWER_NOT_IN_OPTIONS" in results[0]["flags"]

        # Test confidence calculation
        # Baseline confidence without penalty
        base_res = compute_confidence(
            model_confidence=0.90,
            question_number="1",
            question_text="Valid length question text here",
            question_type="mcq_single",
            options=options,
            has_image=False,
            has_table=False,
            existing_flags=[],
            answer_status="matched",
            page_quality=1.0,
        )
        assert base_res.confidence == 0.90
        assert base_res.status == "extracted"

        # With ANSWER_NOT_IN_OPTIONS:
        penalized_res = compute_confidence(
            model_confidence=0.90,
            question_number="1",
            question_text="Valid length question text here",
            question_type="mcq_single",
            options=options,
            has_image=False,
            has_table=False,
            existing_flags=["ANSWER_NOT_IN_OPTIONS"],
            answer_status="matched",
            page_quality=1.0,
        )
        # Confidence lowered by 0.20 (0.90 - 0.20 = 0.70)
        assert penalized_res.confidence == 0.70
        # Forced to needs_review because ANSWER_NOT_IN_OPTIONS is an error flag
        assert penalized_res.status == "needs_review"
        assert "ANSWER_NOT_IN_OPTIONS" in penalized_res.flags


class TestEdgeCase6KeyEntryForNonExistentQuestion:
    """6. Key entry for Q99 when no Q99 exists -> review item."""

    def test_unmatched_key_entry_generates_review_item(self):
        session = SyncSessionLocal()

        user = User(
            id=uuid.uuid4(),
            email=f"edge6_{uuid.uuid4().hex[:6]}@example.com",
            password_hash=hash_password("pw123"),
        )
        doc = Document(
            id=uuid.uuid4(),
            owner_id=user.id,
            role=DocumentRole.question_paper,
            original_filename="dummy.pdf",
            stored_path="dummy.pdf",
            mime_type="application/pdf",
            sha256="0" * 64,
            size_bytes=100,
            page_count=1,
            status=DocumentStatus.queued,
        )
        session.add_all([user, doc])
        session.commit()

        # Questions only have Q1 and Q2
        q1 = Question(
            id=uuid.uuid4(),
            document_id=doc.id,
            question_number="1",
            question_text="Question 1 text",
            question_type=QuestionType.mcq_single,
            confidence=0.90,
        )
        q2 = Question(
            id=uuid.uuid4(),
            document_id=doc.id,
            question_number="2",
            question_text="Question 2 text",
            question_type=QuestionType.mcq_single,
            confidence=0.90,
        )
        # Key entry has Q99 which does NOT exist in questions
        entry_q99 = AnswerKeyEntry(
            id=uuid.uuid4(),
            document_id=doc.id,
            question_number="99",
            answer_value="C",
            source_page=1,
            raw_text="99: C",
        )
        session.add_all([q1, q2, entry_q99])
        session.commit()

        from app.workers.tasks import _match_answers_for_document
        review_items = []
        _match_answers_for_document(session, doc, [q1, q2], review_items)

        # Must create review item with UNMATCHED_ANSWER_KEY
        unmatched_items = [r for r in review_items if r.code == "UNMATCHED_ANSWER_KEY"]
        assert len(unmatched_items) == 1
        assert "99=C" in unmatched_items[0].message
        assert unmatched_items[0].document_id == doc.id
        session.close()
