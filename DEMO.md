# Demo Results & Output Evidence

**Extractor used:** `fake`

> ℹ️ Generated using the deterministic `FakeExtractor` for fully reproducible offline evaluation.

## 1. Scenario Execution Matrix

| # | Scenario | Result | Output File |
|---|----------|--------|-------------|
| 1 | Register + Login | ✅ PASS | `01_register.json / 02_login.json` |
| 2 | Upload PDF | ✅ PASS | `03_upload_pdf.json / 04_pdf_processed.json` |
| 3 | Upload Image | ✅ PASS | `05_upload_image.json` |
| 4 | Question Extraction | ✅ PASS | `06_questions_list.json / 07_question_detail.json` |
| 5 | Answer Key | ✅ PASS | `08_answer_key.json` |
| 6 | Review Items | ✅ PASS | `09_review_items.json` |
| 7 | Cross-page Question | ✅ PASS | `10_upload_crosspage.json / 11_crosspage_questions.json` |
| 8 | Groups + Answer Key | ✅ PASS | `12_create_group.json - 16_group_questions.json` |
| 9 | Invalid Upload Rejection | ✅ PASS | `17_invalid_upload.json` |
| 10 | Health Check | ✅ PASS | `18_health.json` |

## 2. Real API Output Samples (Extracted directly from running service)

### A. Registration & JWT Auth
```json
// POST /api/v1/auth/register
{
  "id": "e07edfbb-32c0-4d18-8107-9ad2f05cf551",
  "email": "demo_ec3f61@example.com"
}
```
```json
// POST /api/v1/auth/login -> JWT Bearer Token
{
  "token_type": "bearer",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5c..."
}
```

### B. Asynchronous Ingestion & Document Status
```json
// GET /api/v1/documents/{id}
{
  "id": "aaa07c8b-e42e-495f-89c6-eb92e5123813",
  "group_id": null,
  "role": "mixed",
  "original_filename": "01_clean_digital.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 2666,
  "page_count": 3,
  "status": "completed_with_warnings",
  "progress_pct": 100,
  "error_message": null,
  "created_at": "2026-09-19T16:56:33.203303",
  "updated_at": "2026-09-19T16:56:35.172950"
}
```

### C. Structured Question Extraction & Answer Matching
```json
// Sample extracted question from document (total 9 questions):
{
  "id": "82b2dd4e-218c-4b00-b4fe-28e6d01e6e37",
  "document_id": "aaa07c8b-e42e-495f-89c6-eb92e5123813",
  "group_id": null,
  "question_number": "1",
  "question_text": "What is the capital of Country 1?",
  "question_type": "mcq_single",
  "options": [
    {
      "label": "A",
      "text": "City Alpha 1"
    },
    {
      "label": "B",
      "text": "City Beta 1"
    },
    {
      "label": "C",
      "text": "City Gamma 1"
    },
    {
      "label": "D",
      "text": "City Delta 1"
    }
  ],
  "has_image": false,
  "has_table": false,
  "source_pages": [
    1
  ],
  "answer": {
    "value": "A",
    "source_document_id": "aaa07c8b-e42e-495f-89c6-eb92e5123813",
    "source_page": 3,
    "match_method": "normalized_number"
  },
  "answer_status": "matched",
  "confidence": 0.92,
  "status": "extracted",
  "flags": [],
  "reviewed": false,
  "created_at": "2026-09-19T16:56:35.144618"
}
```

### D. Cross-Page Question Stitching Evidence
Question spans pages: `[1, 2]` with flags `['STITCHED_ACROSS_PAGES', 'BAD_OPTION_COUNT']`:
```json
{
  "id": "7c9854d8-2ce9-48a6-9e6c-886c5ede6773",
  "document_id": "22c872ff-625a-4bc2-911d-760ffb2ac157",
  "group_id": null,
  "question_number": "5",
  "question_text": "What is the capital of Country 5? ...which was established in the year 1900 + 6?",
  "question_type": "mcq_single",
  "options": [
    {
      "label": "A",
      "text": "City Alpha 5"
    },
    {
      "label": "B",
      "text": "City Beta 5"
    },
    {
      "label": "C",
      "text": "City Gamma 5"
    },
    {
      "label": "D",
      "text": "City Delta 5"
    },
    {
      "label": "A",
      "text": "City Alpha 6"
    },
    {
      "label": "B",
      "text": "City Beta 6"
    },
    {
      "label": "C",
      "text": "City Gamma 6"
    },
    {
      "label": "D",
      "text": "City Delta 6"
    }
  ],
  "has_image": false,
  "has_table": false,
  "source_pages": [
    1,
    2
  ],
  "answer": null,
  "answer_status": "not_found",
  "confidence": 0.5,
  "status": "partial",
  "flags": [
    "STITCHED_ACROSS_PAGES",
    "BAD_OPTION_COUNT"
  ],
  "reviewed": false,
  "created_at": "2026-09-19T16:56:36.512066"
}
```

### E. Review Queue (Handling Uncertainty Honestly)
```json
// GET /api/v1/documents/{id}/review-items
[
  {
    "id": "87d65be4-0cf1-4745-b00a-bf37bda9c1db",
    "document_id": "aaa07c8b-e42e-495f-89c6-eb92e5123813",
    "question_id": null,
    "severity": "info",
    "code": "UNMATCHED_ANSWER_KEY",
    "message": "Answer key entry '6=B' has no matching question",
    "page_number": 3,
    "resolved": false,
    "created_at": "2026-09-19T16:56:35.171720"
  },
  {
    "id": "97635dd1-96cf-4aab-9b8e-3b7b4a836abe",
    "document_id": "aaa07c8b-e42e-495f-89c6-eb92e5123813",
    "question_id": null,
    "severity": "info",
    "code": "UNMATCHED_ANSWER_KEY",
    "message": "Answer key entry '99=C' has no matching question",
    "page_number": 3,
    "resolved": false,
    "created_at": "2026-09-19T16:56:35.171724"
  },
  {
    "id": "bbc1836a-4c27-4ce7-9a80-c75f3a398029",
    "document_id": "aaa07c8b-e42e-495f-89c6-eb92e5123813",
    "question_id": "5391f1f6-0988-4162-8fbe-7d11f4c4e06c",
    "severity": "warning",
    "code": "LOW_CONFIDENCE",
    "message": "Question 10: confidence 0.80, flags: MISSING_CONTINUATION",
    "page_number": 2,
    "resolved": false,
    "created_at": "2026-09-19T16:56:35.171726"
  }
]
```

### F. Strict File Validation & RFC 7807 Error Envelope
```json
// POST /api/v1/documents with invalid signature (EXE with .pdf extension):
{
  "error": {
    "code": "UNSUPPORTED_MEDIA",
    "message": "Unsupported file type: unknown"
  }
}
```

## 3. JSON Output File Manifest

- `01_register.json` (91 bytes)
- `02_login.json` (218 bytes)
- `03_upload_pdf.json` (123 bytes)
- `04_pdf_processed.json` (403 bytes)
- `05_upload_image.json` (123 bytes)
- `06_questions_list.json` (10693 bytes)
- `07_question_detail.json` (949 bytes)
- `08_answer_key.json` (2214 bytes)
- `09_review_items.json` (1161 bytes)
- `10_upload_crosspage.json` (123 bytes)
- `11_crosspage_questions.json` (9163 bytes)
- `12_create_group.json` (155 bytes)
- `13_add_doc_to_group.json` (443 bytes)
- `14_upload_answer_key.json` (123 bytes)
- `15_rematch.json` (58 bytes)
- `16_group_questions.json` (10999 bytes)
- `17_invalid_upload.json` (106 bytes)
- `18_health.json` (112 bytes)