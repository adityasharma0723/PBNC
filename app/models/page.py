"""Page model. One row per rendered page of a document. Stores the
extracted text layer, quality metrics, and classification results.
image_path is relative to UPLOAD_DIR and uses UUID naming."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Boolean, DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class PageType(str, enum.Enum):
    questions = "questions"
    answer_key = "answer_key"
    mixed = "mixed"
    blank = "blank"
    other = "other"

class Page(Base):
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rotation_applied: Mapped[int] = mapped_column(Integer, default=0)
    page_type: Mapped[PageType] = mapped_column(
        Enum(PageType), default=PageType.other, nullable=False
    )
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    document = relationship("Document", back_populates="pages")

    __table_args__ = (

        {"comment": "One rendered page per document"},
    )
