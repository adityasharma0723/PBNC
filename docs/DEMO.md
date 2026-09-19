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
  "id": "f50b9566-5d98-42fb-8fa1-ae8eb844e37f",
  "email": "demo_30ec79@example.com"
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
  "id": "594aa56b-dee8-49e9-9686-0600d15226e0",
  "group_id": null,
  "role": "mixed",
  "original_filename": "01_clean_digital.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 2666,
  "page_count": 3,
  "status": "completed_with_warnings",
  "progress_pct": 100,
  "error_message": null,
  "created_at": "2026-09-19T17:20:19.243664",
  "updated_at": "2026-09-19T17:20:23.717724"
}
```

### C. Structured Question Extraction & Answer Matching
```json
// Sample extracted question from document (total 9 questions):
{
  "id": "2f0a110f-5298-49b8-a812-99b80f8e7ede",
  "document_id": "594aa56b-dee8-49e9-9686-0600d15226e0",
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
    "source_document_id": "594aa56b-dee8-49e9-9686-0600d15226e0",
    "source_page": 3,
    "match_method": "normalized_number"
  },
  "answer_status": "matched",
  "confidence": 0.92,
  "status": "extracted",
  "flags": [],
  "reviewed": false,
  "created_at": "2026-09-19T17:20:23.664821"
}
```

### D. Cross-Page Question Stitching Evidence
Question spans pages: `[1, 2]` with flags `['STITCHED_ACROSS_PAGES', 'BAD_OPTION_COUNT']`:
```json
{
  "id": "3a40d909-28f4-4923-82aa-ece854a779bd",
  "document_id": "bceb8155-a6f3-4e75-a472-e1b0df96675a",
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
  "created_at": "2026-09-19T17:20:26.783948"
}
```

### E. Review Queue (Handling Uncertainty Honestly)
```json
// GET /api/v1/documents/{id}/review-items
[
  {
    "id": "69b411ca-2f8d-4682-9da3-2f19f33b87e6",
    "document_id": "594aa56b-dee8-49e9-9686-0600d15226e0",
    "question_id": null,
    "severity": "info",
    "code": "UNMATCHED_ANSWER_KEY",
    "message": "Answer key entry '6=B' has no matching question",
    "page_number": 3,
    "resolved": false,
    "created_at": "2026-09-19T17:20:23.715086"
  },
  {
    "id": "f5b5c657-93b7-4539-b45f-1224a545c164",
    "document_id": "594aa56b-dee8-49e9-9686-0600d15226e0",
    "question_id": null,
    "severity": "info",
    "code": "UNMATCHED_ANSWER_KEY",
    "message": "Answer key entry '99=C' has no matching question",
    "page_number": 3,
    "resolved": false,
    "created_at": "2026-09-19T17:20:23.715101"
  },
  {
    "id": "71ce9d43-b222-4f9a-9c0c-0dfde4ed4a5e",
    "document_id": "594aa56b-dee8-49e9-9686-0600d15226e0",
    "question_id": "1e81ead1-b998-4d30-8aae-a8d85a484295",
    "severity": "warning",
    "code": "LOW_CONFIDENCE",
    "message": "Question 10: confidence 0.80, flags: MISSING_CONTINUATION",
    "page_number": 2,
    "resolved": false,
    "created_at": "2026-09-19T17:20:23.715109"
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