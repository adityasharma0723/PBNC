"""Document and related response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.document import DocumentRole, DocumentStatus
from app.models.page import PageType
from app.models.question import AnswerStatus, QuestionStatus, QuestionType
from app.models.review import Severity

class DocumentResponse(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID | None = None
    role: DocumentRole
    original_filename: str
    mime_type: str
    size_bytes: int
    page_count: int | None = None
    status: DocumentStatus
    progress_pct: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int

class DocumentUploadResponse(BaseModel):
    id: uuid.UUID
    status: DocumentStatus
    message: str = "Document queued for processing"

    model_config = {"json_schema_extra": {
        "example": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "queued",
            "message": "Document queued for processing",
        }
    }}

class PageResponse(BaseModel):
    id: uuid.UUID
    page_number: int
    has_text_layer: bool
    quality_score: float | None = None
    rotation_applied: int
    page_type: PageType
    image_url: str | None = None
    raw_text: str | None = None

    model_config = {"from_attributes": True}

class OptionSchema(BaseModel):
    label: str
    text: str

class AnswerSchema(BaseModel):
    value: str
    source_document_id: uuid.UUID | None = None
    source_page: int | None = None
    match_method: str | None = None

class QuestionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    group_id: uuid.UUID | None = None
    question_number: str | None = None
    question_text: str
    question_type: QuestionType
    options: list[OptionSchema] | None = None
    has_image: bool
    has_table: bool
    source_pages: list[int] | None = None
    answer: AnswerSchema | None = None
    answer_status: AnswerStatus
    confidence: float
    status: QuestionStatus
    flags: list[str] | None = None
    reviewed: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}

class QuestionListResponse(BaseModel):
    items: list[QuestionResponse]
    total: int

class QuestionUpdateRequest(BaseModel):
    """Allow reviewer to correct extracted data."""
    question_text: str | None = None
    question_type: QuestionType | None = None
    options: list[OptionSchema] | None = None
    answer: AnswerSchema | None = None
    question_number: str | None = None

class ReviewItemResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    question_id: uuid.UUID | None = None
    severity: Severity
    code: str
    message: str
    page_number: int | None = None
    resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class ReviewItemUpdate(BaseModel):
    resolved: bool

class AnswerKeyEntryResponse(BaseModel):
    id: uuid.UUID
    question_number: str
    answer_value: str
    source_page: int | None = None
    matched_question_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}

class GroupCreateRequest(BaseModel):
    name: str

    model_config = {"json_schema_extra": {"example": {"name": "Math Final 2024"}}}

class GroupResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    document_count: int = 0

    model_config = {"from_attributes": True}

class GroupAddDocumentRequest(BaseModel):
    document_id: uuid.UUID
    role: DocumentRole = DocumentRole.unknown
