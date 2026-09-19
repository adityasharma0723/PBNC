"""Review items router: list, resolve review items, and answer key view."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.errors import NotFoundError
from app.models.document import Document
from app.models.question import Question
from app.models.review import ReviewItem, Severity
from app.models.answer_key import AnswerKeyEntry
from app.models.user import User
from app.schemas.document import (
    ReviewItemResponse,
    ReviewItemUpdate,
    AnswerKeyEntryResponse,
)

router = APIRouter(tags=["Review"])


@router.get(
    "/documents/{document_id}/review-items",
    response_model=list[ReviewItemResponse],
    summary="List review items for a document",
)
async def list_review_items(
    document_id: uuid.UUID,
    severity: Severity | None = None,
    resolved: bool | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_doc_ownership(db, document_id, user.id)

    q = select(ReviewItem).where(ReviewItem.document_id == document_id)
    if severity:
        q = q.where(ReviewItem.severity == severity)
    if resolved is not None:
        q = q.where(ReviewItem.resolved == resolved)

    q = q.order_by(ReviewItem.created_at)
    result = await db.execute(q)
    items = result.scalars().all()
    return [ReviewItemResponse.model_validate(ri) for ri in items]


@router.patch(
    "/review-items/{review_item_id}",
    response_model=ReviewItemResponse,
    summary="Resolve or unresolve a review item",
)
async def update_review_item(
    review_item_id: uuid.UUID,
    body: ReviewItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get review item and verify ownership through document
    result = await db.execute(
        select(ReviewItem).join(Document).where(
            ReviewItem.id == review_item_id,
            Document.owner_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise NotFoundError("Review item")

    item.resolved = body.resolved
    await db.commit()
    await db.refresh(item)
    return ReviewItemResponse.model_validate(item)


@router.get(
    "/documents/{document_id}/answer-key",
    response_model=list[AnswerKeyEntryResponse],
    summary="Get parsed answer key entries for a document",
)
async def get_answer_key(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_doc_ownership(db, document_id, user.id)

    result = await db.execute(
        select(AnswerKeyEntry)
        .where(AnswerKeyEntry.document_id == document_id)
        .order_by(AnswerKeyEntry.question_number)
    )
    entries = result.scalars().all()
    return [AnswerKeyEntryResponse.model_validate(e) for e in entries]


async def _verify_doc_ownership(db: AsyncSession, doc_id: uuid.UUID, owner_id: uuid.UUID):
    result = await db.execute(
        select(Document.id).where(Document.id == doc_id, Document.owner_id == owner_id)
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Document")
