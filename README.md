# DocIntel – Document Intelligence & Question Extraction Service

A production-oriented backend service that accepts PDFs and images of exam/question-bank material, processes them asynchronously, and exposes structured, system-independent question data via a REST API.

## ⚡ Quick Start

```bash
# 1. Clone and configure
git clone <repo-url> && cd docintel
cp .env.example .env
# Edit .env: set SECRET_KEY to a random string
# Optionally set LLM_API_KEY for real extraction (Gemini)

# 2. Build and run
docker compose up --build

# 3. Access
# API:     http://localhost:8000
# Swagger: http://localhost:8000/docs
# Health:  http://localhost:8000/health
```

Migrations run automatically on startup. No manual steps needed.

## 🔑 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | JWT signing secret; generate with `openssl rand -hex 32` |
| `EXTRACTOR` | `fake` | `llm` for Gemini extraction, `fake` for offline/testing |
| `LLM_API_KEY` | (empty) | Google Gemini API key (required when EXTRACTOR=llm) |
| `LLM_MODEL` | `gemini-2.0-flash` | Gemini model to use |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum file upload size |
| `MAX_PAGES` | `200` | Maximum pages per PDF |
| `RENDER_DPI` | `200` | DPI for page rendering |
| `CONFIDENCE_HIGH` | `0.80` | Threshold for "extracted" status |
| `CONFIDENCE_LOW` | `0.50` | Threshold for "partial" status |
| `CELERY_CONCURRENCY` | `4` | Celery worker concurrency |
| `DATABASE_URL` | (see .env.example) | Async PostgreSQL URL |
| `REDIS_URL` | (see .env.example) | Redis URL |

## 🧪 Running Tests

Tests run offline using the FakeExtractor and an in-memory SQLite database:

```bash
# Inside the container
docker compose run --rm api python -m pytest tests/ -v

# Or with make
make test
```

## 🎯 Running the Demo

```bash
# 1. Generate sample documents
docker compose exec api python scripts/make_samples.py

# 2. Run demo scenarios
docker compose exec api python scripts/run_demo.py

# Results saved to outputs/ and docs/DEMO.md
```

## 📡 AI/OCR Services Disclosure

This service uses **Google Gemini** (a vision-capable LLM) for document extraction. When `EXTRACTOR=llm`:
- Document pages are sent to the Gemini API for question extraction
- An API key is required (`LLM_API_KEY` environment variable)
- Document content is transmitted to Google's servers

When `EXTRACTOR=fake`, a deterministic offline extractor is used (no external API calls).

## 🏗️ Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation including:
- System architecture diagram
- Processing pipeline details
- Confidence scoring formula
- Security design
- Scalability considerations

## 📋 API Overview

All endpoints under `/api/v1`, JWT bearer auth required (except register/login).

### Auth
- `POST /api/v1/auth/register` – Register
- `POST /api/v1/auth/login` – Login, receive JWT

### Documents
- `POST /api/v1/documents` – Upload (multipart, 202 Accepted)
- `GET /api/v1/documents` – List your documents
- `GET /api/v1/documents/{id}` – Document details + status
- `DELETE /api/v1/documents/{id}` – Delete document
- `GET /api/v1/documents/{id}/pages` – List pages
- `GET /api/v1/documents/{id}/pages/{n}` – Page detail

### Questions
- `GET /api/v1/documents/{id}/questions` – List questions (filters: status, min_confidence, has_answer)
- `GET /api/v1/questions/{id}` – Question detail
- `PATCH /api/v1/questions/{id}` – Reviewer correction

### Groups
- `POST /api/v1/groups` – Create group
- `GET /api/v1/groups` – List groups
- `GET /api/v1/groups/{id}` – Group detail
- `POST /api/v1/groups/{id}/documents` – Add document to group
- `DELETE /api/v1/groups/{id}/documents/{doc_id}` – Remove from group
- `GET /api/v1/groups/{id}/questions` – Merged question view
- `POST /api/v1/groups/{id}/rematch` – Re-run answer matching

### Review
- `GET /api/v1/documents/{id}/review-items` – List review items
- `PATCH /api/v1/review-items/{id}` – Resolve/unresolve
- `GET /api/v1/documents/{id}/answer-key` – Parsed answer key entries

### Health
- `GET /health` – Database + Redis health check

## 🔒 Security

- Passwords hashed with bcrypt
- JWT tokens with configurable expiry
- Owner-scoped queries (returns 404, not 403, for other users' resources)
- Magic-byte file validation (not extension-based)
- UUID file storage names (path traversal prevention)
- Decompression bomb protection (Pillow MAX_IMAGE_PIXELS)
- Encrypted PDF rejection
- Non-root container execution
- LLM credentials from env only, never logged or returned

## ⚖️ Scaling

```bash
# Scale workers horizontally
docker compose up --scale worker=3
```

Workers are stateless; tasks are idempotent and re-runnable.

## ⚠️ Known Limitations

1. **Table/image extraction**: Images and tables within questions are detected and flagged but not fully parsed. Crop references are stored but content is not extracted.
2. **OCR**: No traditional OCR pipeline; relies on the vision LLM for scanned documents. This works well with Gemini but costs more than Tesseract for high-volume use.
3. **Rate limiting**: Implemented as a note; production deployment should use a Redis-based middleware (e.g., slowapi).
4. **File serving**: Page images are stored but not served via a static file endpoint; a CDN or signed-URL approach is recommended for production.
5. **Concurrent group matching**: If two documents in the same group finish simultaneously, answer matching could have race conditions. Mitigated by the rematch endpoint.
