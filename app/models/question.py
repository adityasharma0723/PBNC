"""Question model. The core output entity. Each row represents one
extracted question with its options, type, answer, and confidence.

Design notes:
- question_number is a string (not int) because real papers use "1a", "Q1", etc.
- answer is nullable JSON; null means "no answer found" (never guess).
- answer_status tracks the matching state independently of confidence.
- flags is a list of machine-readable strings explaining low confidence.
- source_pages is an array of page numbers this question spans.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Boolean, DateTime, Enum, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Dialect-agnostic types that work on both SQLite (tests/offline) and PostgreSQL (production)
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")
ARRAY_INT_TYPE = JSON().with_variant(ARRAY(Integer), "postgresql")


class QuestionType(str, enum.Enum):
    mcq_single = "mcq_single"
    mcq_multiple = "mcq_multiple"
    true_false = "true_false"
    fill_blank = "fill_blank"
    short_answer = "short_answer"
    long_answer = "long_answer"
    unknown = "unknown"


class AnswerStatus(str, enum.Enum):
    matched = "matched"
    unmatched = "unmatched"
    ambiguous = "ambiguous"
    not_found = "not_found"


class QuestionStatus(str, enum.Enum):
    extracted = "extracted"
    partial = "partial"
    needs_review = "needs_review"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_groups.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    question_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType), default=QuestionType.unknown, nullable=False
    )
    options: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    has_image: Mapped[bool] = mapped_column(Boolean, default=False)
    has_table: Mapped[bool] = mapped_column(Boolean, default=False)
    assets: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    source_pages: Mapped[list[int] | None] = mapped_column(ARRAY_INT_TYPE, nullable=True)
    answer: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    answer_status: Mapped[AnswerStatus] = mapped_column(
        Enum(AnswerStatus), default=AnswerStatus.not_found, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[QuestionStatus] = mapped_column(
        Enum(QuestionStatus), default=QuestionStatus.extracted, nullable=False, index=True
    )
    flags: Mapped[list[str] | None] = mapped_column(JSON_TYPE, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    document = relationship("Document", back_populates="questions")
    review_items = relationship("ReviewItem", back_populates="question")
