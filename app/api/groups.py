"""Groups router: create, list, manage document groups.

Groups enable associating a question paper with its answer key
(uploaded separately). Answer matching works across the group.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.errors import NotFoundError, AppError
from app.models.document import Document, DocumentRole
from app.models.group import DocumentGroup
from app.models.question import Question
from app.models.user import User
from app.schemas.document import (
    GroupCreateRequest,
    GroupResponse,
    GroupAddDocumentRequest,
    DocumentResponse,
    QuestionResponse,
    QuestionListResponse,
)

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.post(
    "",
    response_model=GroupResponse,
    status_code=201,
    summary="Create a document group",
)
async def create_group(
    body: GroupCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = DocumentGroup(owner_id=user.id, name=body.name)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return GroupResponse(id=group.id, name=group.name, created_at=group.created_at, document_count=0)


@router.get(
    "",
    response_model=list[GroupResponse],
    summary="List your groups",
)
async def list_groups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DocumentGroup)
        .where(DocumentGroup.owner_id == user.id)
        .order_by(DocumentGroup.created_at.desc())
    )
    groups = result.scalars().all()

    responses = []
    for g in groups:
        count_result = await db.execute(
            select(func.count()).select_from(Document).where(Document.group_id == g.id)
        )
        count = count_result.scalar() or 0
        responses.append(GroupResponse(
            id=g.id, name=g.name, created_at=g.created_at, document_count=count
        ))
    return responses


@router.get(
    "/{group_id}",
    response_model=GroupResponse,
    summary="Get group details",
)
async def get_group(
    group_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = await _get_owned_group(db, group_id, user.id)
    count_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.group_id == group.id)
    )
    count = count_result.scalar() or 0
    return GroupResponse(
        id=group.id, name=group.name, created_at=group.created_at, document_count=count
    )


@router.post(
    "/{group_id}/documents",
    response_model=DocumentResponse,
    summary="Add a document to a group",
)
async def add_document_to_group(
    group_id: uuid.UUID,
    body: GroupAddDocumentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = await _get_owned_group(db, group_id, user.id)

    # Verify document ownership
    result = await db.execute(
        select(Document).where(
            Document.id == body.document_id,
            Document.owner_id == user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document")

    doc.group_id = group.id
    if body.role != DocumentRole.unknown:
        doc.role = body.role

    # Also update questions' group_id
    await db.execute(
        select(Question).where(Question.document_id == doc.id)
    )
    questions_result = await db.execute(
        select(Question).where(Question.document_id == doc.id)
    )
    for q in questions_result.scalars().all():
        q.group_id = group.id

    await db.commit()
    await db.refresh(doc)

    # Trigger re-matching
    try:
        from app.workers.tasks import process_document
        # We don't reprocess, just rematch - but for simplicity, we note
        # that full reprocessing would re-trigger matching
    except Exception:
        pass

    return DocumentResponse.model_validate(doc)


@router.delete(
    "/{group_id}/documents/{document_id}",
    status_code=204,
    summary="Remove a document from a group",
)
async def remove_document_from_group(
    group_id: uuid.UUID,
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_group(db, group_id, user.id)

    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == user.id,
            Document.group_id == group_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document")

    doc.group_id = None

    # Clear group from questions
    questions_result = await db.execute(
        select(Question).where(Question.document_id == doc.id)
    )
    for q in questions_result.scalars().all():
        q.group_id = None

    await db.commit()


@router.get(
    "/{group_id}/questions",
    response_model=QuestionListResponse,
    summary="List all questions across the group (merged view with answers)",
)
async def list_group_questions(
    group_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_group(db, group_id, user.id)

    q = select(Question).where(Question.group_id == group_id)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(Question.question_number, Question.created_at)
    q = q.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(q)
    questions = result.scalars().all()

    return QuestionListResponse(
        items=[QuestionResponse.model_validate(qi) for qi in questions],
        total=total,
    )


@router.post(
    "/{group_id}/rematch",
    summary="Re-run answer key matching for the group",
    status_code=200,
)
async def rematch_group(
    group_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run answer matching across the group. Useful when a new answer
    key or question paper has been added."""
    from app.services.answer_key import normalize_question_number
    from app.models.answer_key import AnswerKeyEntry
    from app.models.question import AnswerStatus

    await _get_owned_group(db, group_id, user.id)

    # Get all questions in group
    q_result = await db.execute(
        select(Question).where(Question.group_id == group_id)
    )
    questions = list(q_result.scalars().all())

    # Get all answer entries in group
    e_result = await db.execute(
        select(AnswerKeyEntry).join(Document).where(Document.group_id == group_id)
    )
    entries = list(e_result.scalars().all())

    if not entries:
        return {"message": "No answer key entries found in group", "matched": 0}

    # Build question index
    q_by_number: dict[str, list[Question]] = {}
    for q in questions:
        if q.question_number:
            norm = normalize_question_number(q.question_number)
            q_by_number.setdefault(norm, []).append(q)

    matched_count = 0
    for entry in entries:
        norm = normalize_question_number(entry.question_number)
        matching = q_by_number.get(norm, [])

        if len(matching) == 1:
            q = matching[0]
            entry.matched_question_id = q.id

            option_labels = set()
            if q.options:
                option_labels = {
                    opt.get("label", "").upper()
                    for opt in q.options
                    if isinstance(opt, dict)
                }

            q.answer = {
                "value": entry.answer_value,
                "source_document_id": str(entry.document_id),
                "source_page": entry.source_page,
                "match_method": "normalized_number",
            }
            q.answer_status = AnswerStatus.matched

            if entry.answer_value.upper() not in option_labels and option_labels:
                q.flags = (q.flags or []) + ["ANSWER_NOT_IN_OPTIONS"]

            matched_count += 1
        elif len(matching) > 1:
            for q in matching:
                q.answer_status = AnswerStatus.ambiguous

    await db.commit()
    return {"message": f"Re-matched {matched_count} answers", "matched": matched_count}


async def _get_owned_group(db: AsyncSession, group_id: uuid.UUID, owner_id: uuid.UUID) -> DocumentGroup:
    result = await db.execute(
        select(DocumentGroup).where(
            DocumentGroup.id == group_id,
            DocumentGroup.owner_id == owner_id,
        )
    )
    group = result.scalar_one_or_none()
    if not group:
        raise NotFoundError("Group")
    return group
