"""Initial schema – all tables, indexes, and FK constraints.

Revision ID: 001
Revises: None
Create Date: 2024-01-01 00:00:00.000000

Hand-written rather than auto-generated for clarity and control.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # --- document_groups ---
    op.create_table(
        "document_groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_groups_owner_id", "document_groups", ["owner_id"])

    # --- documents ---
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("document_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.Enum("question_paper", "answer_key", "mixed", "unknown", name="documentrole"), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("stored_path", sa.String(512), unique=True, nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("status", sa.Enum("queued", "processing", "completed", "completed_with_warnings", "failed", name="documentstatus"), nullable=False),
        sa.Column("progress_pct", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_documents_group_id", "documents", ["group_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])

    # --- pages ---
    op.create_table(
        "pages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("has_text_layer", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("rotation_applied", sa.Integer, nullable=False, server_default="0"),
        sa.Column("page_type", sa.Enum("questions", "answer_key", "mixed", "blank", "other", name="pagetype"), nullable=False),
        sa.Column("image_path", sa.String(512), nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pages_document_id", "pages", ["document_id"])
    # Unique constraint: one page number per document
    op.create_unique_constraint("uq_pages_document_page", "pages", ["document_id", "page_number"])

    # --- questions ---
    op.create_table(
        "questions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("document_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question_number", sa.String(32), nullable=True),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("question_type", sa.Enum("mcq_single", "mcq_multiple", "true_false", "fill_blank", "short_answer", "long_answer", "unknown", name="questiontype"), nullable=False),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("has_image", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("has_table", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("assets", JSONB, nullable=True),
        sa.Column("source_pages", ARRAY(sa.Integer), nullable=True),
        sa.Column("answer", JSONB, nullable=True),
        sa.Column("answer_status", sa.Enum("matched", "unmatched", "ambiguous", "not_found", name="answerstatus"), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("status", sa.Enum("extracted", "partial", "needs_review", name="questionstatus"), nullable=False),
        sa.Column("flags", JSONB, nullable=True),
        sa.Column("reviewed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_questions_document_id", "questions", ["document_id"])
    op.create_index("ix_questions_group_id", "questions", ["group_id"])
    op.create_index("ix_questions_status", "questions", ["status"])

    # --- review_items ---
    op.create_table(
        "review_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", UUID(as_uuid=True), sa.ForeignKey("questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("severity", sa.Enum("info", "warning", "error", name="severity"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_items_document_id", "review_items", ["document_id"])
    op.create_index("ix_review_items_question_id", "review_items", ["question_id"])
    op.create_index("ix_review_items_code", "review_items", ["code"])

    # --- answer_key_entries ---
    op.create_table(
        "answer_key_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_number", sa.String(32), nullable=False),
        sa.Column("answer_value", sa.String(256), nullable=False),
        sa.Column("source_page", sa.Integer, nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("matched_question_id", UUID(as_uuid=True), sa.ForeignKey("questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_answer_key_entries_document_id", "answer_key_entries", ["document_id"])
    op.create_index("ix_answer_key_entries_matched_question_id", "answer_key_entries", ["matched_question_id"])


def downgrade() -> None:
    op.drop_table("answer_key_entries")
    op.drop_table("review_items")
    op.drop_table("questions")
    op.drop_table("pages")
    op.drop_table("documents")
    op.drop_table("document_groups")
    op.drop_table("users")

    # Drop enums
    for name in [
        "documentrole", "documentstatus", "pagetype", "questiontype",
        "answerstatus", "questionstatus", "severity",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {name}")
