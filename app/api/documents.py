"""Documents router: upload, list, get, delete.

Upload flow:
1. Stream to memory with size cap (reject early if over limit).
2. Validate magic bytes, page count, encryption, decompression bombs.
3. Store with UUID name, create DB record, enqueue Celery task.
4. Return 202 Accepted with document ID.

All queries filter by owner_id. Accessing another user's document returns 404.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Response, UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.core.errors import AppError, NotFoundError, ValidationError
from app.models.document import Document, DocumentRole, DocumentStatus
from app.models.group import DocumentGroup
from app.models.page import Page
from app.models.user import User
from app.schemas.document import (
    DocumentResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    PageResponse,
)
from app.services.file_validation import validate_file
from app.services.storage import store_file, get_extension_for_mime, delete_file

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=202,
    summary="Upload a document for processing",
    responses={
        413: {"description": "File too large"},
        415: {"description": "Unsupported file type"},
        422: {"description": "Validation error (corrupt, encrypted, etc.)"},
    },
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    group_id: uuid.UUID | None = Form(None),
    role: DocumentRole = Form(DocumentRole.unknown),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    max_bytes = settings.max_upload_bytes
    chunks = []
    total = 0
    while True:
        chunk = await file.read(8192)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            from app.core.errors import FileTooLargeError
            raise FileTooLargeError(settings.MAX_UPLOAD_SIZE_MB)
        chunks.append(chunk)

    file_bytes = b"".join(chunks)

    if not file_bytes:
        raise ValidationError("Empty file uploaded")

    validation = validate_file(file_bytes)

    if group_id:
        result = await db.execute(
            select(DocumentGroup).where(
                DocumentGroup.id == group_id,
                DocumentGroup.owner_id == user.id,
            )
        )
        if not result.scalar_one_or_none():
            group_id = None

    extension = get_extension_for_mime(validation.mime_type)
    stored_path, sha256 = store_file(file_bytes, extension)

    doc = Document(
        owner_id=user.id,
        group_id=group_id,
        role=role,
        original_filename=file.filename or "unknown",
        stored_path=stored_path,
        mime_type=validation.mime_type,
        sha256=sha256,
        size_bytes=validation.size_bytes,
        page_count=validation.page_count,
        status=DocumentStatus.queued,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    from app.workers.tasks import process_document
    if settings.DATABASE_URL.startswith("sqlite"):
        background_tasks.add_task(process_document, str(doc.id))
    else:
        try:
            process_document.apply_async(args=[str(doc.id)], retry=False)
        except Exception:
            background_tasks.add_task(process_document, str(doc.id))

    return DocumentUploadResponse(id=doc.id, status=doc.status)

@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List your documents",
)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size

    count_q = select(func.count()).select_from(Document).where(Document.owner_id == user.id)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Document)
        .where(Document.owner_id == user.id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(q)
    docs = result.scalars().all()

    return DocumentListResponse(items=[DocumentResponse.model_validate(d) for d in docs], total=total)

@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details",
)
async def get_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_owned_document(db, document_id, user.id)
    return DocumentResponse.model_validate(doc)

@router.delete(
    "/{document_id}",
    status_code=204,
    summary="Delete a document and its data",
)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_owned_document(db, document_id, user.id)

    delete_file(doc.stored_path)

    result = await db.execute(select(Page).where(Page.document_id == doc.id))
    for page in result.scalars().all():
        if page.image_path:
            delete_file(page.image_path)

    await db.delete(doc)
    await db.commit()

@router.get(
    "/{document_id}/pages",
    response_model=list[PageResponse],
    summary="List pages of a document",
)
async def list_pages(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_owned_document(db, document_id, user.id)
    result = await db.execute(
        select(Page)
        .where(Page.document_id == doc.id)
        .order_by(Page.page_number)
    )
    pages = result.scalars().all()
    return [PageResponse.model_validate(p) for p in pages]

@router.get(
    "/{document_id}/pages/{page_number}",
    response_model=PageResponse,
    summary="Get a specific page",
)
async def get_page(
    document_id: uuid.UUID,
    page_number: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_owned_document(db, document_id, user.id)
    result = await db.execute(
        select(Page).where(
            Page.document_id == doc.id,
            Page.page_number == page_number,
        )
    )
    page = result.scalar_one_or_none()
    if not page:
        raise NotFoundError("Page")
    return PageResponse.model_validate(page)

async def _get_owned_document(
    db: AsyncSession, document_id: uuid.UUID, owner_id: uuid.UUID
) -> Document:
    """Fetch a document owned by the given user. Returns 404 for missing
    OR for documents owned by another user (no information leakage)."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == owner_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document")
    return doc
