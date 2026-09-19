"""Questions router: list, get, update questions."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.errors import NotFoundError
from app.models.document import Document
from app.models.question import Question, QuestionStatus, AnswerStatus, QuestionType
from app.models.user import User
from app.schemas.document import (
    QuestionResponse,
    QuestionListResponse,
    QuestionUpdateRequest,
)

router = APIRouter(tags=["Questions"])


@router.get(
    "/documents/{document_id}/questions",
    response_model=QuestionListResponse,
    summary="List questions from a document",
)
async def list_document_questions(
    document_id: uuid.UUID,
    status: QuestionStatus | None = None,
    min_confidence: float | None = None,
    has_answer: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify document ownership
    await _verify_doc_ownership(db, document_id, user.id)

    q = select(Question).where(Question.document_id == document_id)

    if status:
        q = q.where(Question.status == status)
    if min_confidence is not None:
        q = q.where(Question.confidence >= min_confidence)
    if has_answer is True:
        q = q.where(Question.answer.isnot(None))
    elif has_answer is False:
        q = q.where(Question.answer.is_(None))

    # Count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch with pagination
    q = q.order_by(Question.created_at).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    questions = result.scalars().all()

    return QuestionListResponse(
        items=[QuestionResponse.model_validate(qi) for qi in questions],
        total=total,
    )


@router.get(
    "/questions/{question_id}",
    response_model=QuestionResponse,
    summary="Get a single question",
)
async def get_question(
    question_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = await _get_owned_question(db, question_id, user.id)
    return QuestionResponse.model_validate(q)


@router.patch(
    "/questions/{question_id}",
    response_model=QuestionResponse,
    summary="Update a question (reviewer correction)",
)
async def update_question(
    question_id: uuid.UUID,
    body: QuestionUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = await _get_owned_question(db, question_id, user.id)

    if body.question_text is not None:
        q.question_text = body.question_text
    if body.question_type is not None:
        q.question_type = body.question_type
    if body.options is not None:
        q.options = [opt.model_dump() for opt in body.options]
    if body.answer is not None:
        q.answer = body.answer.model_dump()
        q.answer_status = AnswerStatus.matched
    if body.question_number is not None:
        q.question_number = body.question_number

    q.reviewed = True
    await db.commit()
    await db.refresh(q)
    return QuestionResponse.model_validate(q)


async def _verify_doc_ownership(db: AsyncSession, doc_id: uuid.UUID, owner_id: uuid.UUID):
    result = await db.execute(
        select(Document.id).where(Document.id == doc_id, Document.owner_id == owner_id)
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Document")


async def _get_owned_question(db: AsyncSession, question_id: uuid.UUID, owner_id: uuid.UUID) -> Question:
    """Get a question, verifying ownership through the document."""
    result = await db.execute(
        select(Question).join(Document).where(
            Question.id == question_id,
            Document.owner_id == owner_id,
        )
    )
    q = result.scalar_one_or_none()
    if not q:
        raise NotFoundError("Question")
    return q
