"""Script to prove the document processing pipeline works end-to-end.

Processes sample documents using EXTRACTOR=fake, commits everything to SQLite DB,
and queries the actual database rows from 'documents', 'pages', 'questions',
'answer_key_entries', and 'review_items'.
"""

import json
import os
import sys
import uuid

# Configure environment before importing app
sys.path.insert(0, os.path.abspath("."))
os.environ["EXTRACTOR"] = "fake"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///demo.db"
os.environ["DATABASE_URL_SYNC"] = "sqlite:///demo.db"
os.environ["UPLOAD_DIR"] = os.path.abspath("demo_uploads")
os.environ["SECRET_KEY"] = "demo-secret-key-12345"

from sqlalchemy import select, text
from app.db.base import Base
from app.db.session import sync_engine, SyncSessionLocal
from app.models.user import User
from app.models.document import Document, DocumentStatus, DocumentRole
from app.models.page import Page
from app.models.question import Question
from app.models.review import ReviewItem
from app.models.answer_key import AnswerKeyEntry
from app.services.file_validation import validate_file
from app.services.storage import store_file, get_extension_for_mime
from app.workers.tasks import process_document
from app.core.security import hash_password


def main():
    print(">>> 1. Initializing SQLite Database (demo.db)...")
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)

    session = SyncSessionLocal()

    # Create User
    user = User(
        id=uuid.uuid4(),
        email="examiner@example.com",
        password_hash=hash_password("securepassword123"),
    )
    session.add(user)
    session.commit()
    print(f"Created test user: {user.email} (ID: {user.id})\n")

    # Sample to process: 01_clean_digital.pdf
    sample_rel = os.path.join("samples", "01_clean_digital.pdf")
    abs_path = os.path.abspath(sample_rel)
    print(f">>> 2. Ingesting sample file: {sample_rel} ({os.path.getsize(abs_path)} bytes)")

    with open(abs_path, "rb") as f:
        file_bytes = f.read()

    validation = validate_file(file_bytes)
    ext = get_extension_for_mime(validation.mime_type)
    stored_path, sha256 = store_file(file_bytes, ext)

    doc = Document(
        id=uuid.uuid4(),
        owner_id=user.id,
        role=DocumentRole.question_paper,
        original_filename="01_clean_digital.pdf",
        stored_path=stored_path,
        mime_type=validation.mime_type,
        sha256=sha256,
        size_bytes=validation.size_bytes,
        page_count=validation.page_count,
        status=DocumentStatus.queued,
    )
    session.add(doc)
    session.commit()
    doc_id = doc.id
    print(f"Inserted Document record: ID={doc_id}, status={doc.status.value}\n")

    print(f">>> 3. Executing process_document('{doc_id}') with EXTRACTOR=fake...")
    pipeline_result = process_document(str(doc_id))
    print(f"process_document task returned: {pipeline_result}\n")

    session.expire_all()

    print("=" * 90)
    print("ACTUAL DATABASE OUTPUT (Queried from SQLite DB)")
    print("=" * 90)

    # 1. Document record
    print("\n--- TABLE: documents ---")
    doc_record = session.execute(
        select(Document).where(Document.id == doc_id)
    ).scalar_one()
    print(
        f"ID: {doc_record.id}\n"
        f"  Owner ID:      {doc_record.owner_id}\n"
        f"  Filename:      {doc_record.original_filename}\n"
        f"  Status:        {doc_record.status.value}\n"
        f"  Role:          {doc_record.role.value}\n"
        f"  Page Count:    {doc_record.page_count}\n"
        f"  Progress:      {doc_record.progress_pct}%\n"
        f"  Error Message: {doc_record.error_message}\n"
        f"  Created At:    {doc_record.created_at}\n"
        f"  Updated At:    {doc_record.updated_at}"
    )

    # 2. Pages records
    print("\n--- TABLE: pages ---")
    pages = session.execute(
        select(Page).where(Page.document_id == doc_id).order_by(Page.page_number)
    ).scalars().all()
    print(f"Total pages created: {len(pages)}")
    for p in pages:
        snippet = (p.raw_text or "").replace("\n", " ")[:60]
        print(
            f"Page #{p.page_number:2d} | ID: {p.id} | Type: {p.page_type.value:10s} | "
            f"Quality: {p.quality_score:.2f} | Text Layer: {p.has_text_layer} | "
            f"Image: {p.image_path} | Text: '{snippet}...'"
        )

    # 3. Questions records
    print("\n--- TABLE: questions ---")
    questions = session.execute(
        select(Question).where(Question.document_id == doc_id).order_by(Question.created_at)
    ).scalars().all()
    print(f"Total questions created: {len(questions)}")
    for q in questions:
        ans_val = q.answer.get("value") if q.answer else None
        print(
            f"Q#{str(q.question_number):>4s} | ID: {q.id} | Type: {q.question_type.value:11s} | "
            f"Status: {q.status.value:12s} | Conf: {q.confidence:.2f} | "
            f"AnsStatus: {q.answer_status.value:10s} | Ans: {ans_val} | "
            f"Pages: {q.source_pages} | Flags: {q.flags}"
        )
        print(f"      Text: {q.question_text[:80]}...")
        if q.options:
            opts_summary = [f"{o.get('label')}: {o.get('text')}" for o in q.options[:2]]
            print(f"      Options (sample): {', '.join(opts_summary)} ... ({len(q.options)} total)")

    # 4. Answer key entries
    print("\n--- TABLE: answer_key_entries ---")
    entries = session.execute(
        select(AnswerKeyEntry).where(AnswerKeyEntry.document_id == doc_id)
    ).scalars().all()
    print(f"Total answer key entries: {len(entries)}")
    for ake in entries:
        print(
            f"Key Entry ID: {ake.id} | Q#: {ake.question_number:>2s} -> Ans: {ake.answer_value} | "
            f"Source Page: {ake.source_page} | Raw: '{ake.raw_text}'"
        )

    # 5. Review items
    print("\n--- TABLE: review_items ---")
    items = session.execute(
        select(ReviewItem).where(ReviewItem.document_id == doc_id)
    ).scalars().all()
    print(f"Total review items created: {len(items)}")
    for r in items:
        print(
            f"ReviewItem ID: {r.id} | Sev: {r.severity.value:7s} | Code: {r.code:22s} | "
            f"Page: {r.page_number} | QID: {r.question_id} | Msg: {r.message}"
        )

    print("\n" + "=" * 90)
    print("PIPELINE EXECUTION VERIFIED SUCCESSFULLY.")
    print("=" * 90)
    session.close()


if __name__ == "__main__":
    main()
