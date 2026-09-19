"""FastAPI application entry point.

Registers routers, exception handlers, and the health endpoint.
Exception handlers enforce the consistent error envelope on ALL errors.
"""

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text

from app.core.config import settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from app.core.logging import setup_logging
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.questions import router as questions_router
from app.api.groups import router as groups_router
from app.api.review import router as review_router
from app.db.session import async_engine


setup_logging(settings.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    yield
    await async_engine.dispose()


app = FastAPI(
    title="DocIntel – Document Intelligence & Question Extraction",
    description=(
        "Upload exam PDFs and images, extract structured questions with "
        "answers and confidence scores. Uses a vision-capable LLM (Gemini) "
        "for extraction. See /docs for full API reference."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Exception handlers (order matters: most specific first) ---
app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)

# --- Routers ---
app.include_router(auth_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(questions_router, prefix="/api/v1")
app.include_router(groups_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")


# --- Health check ---
@app.get("/health", tags=["Health"], summary="Health check (DB + Redis)")
async def health():
    checks = {}

    # Database
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"

    # Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {type(e).__name__}"

    status = "healthy" if all(v == "ok" for v in checks.values()) else "unhealthy"
    return {"status": status, "checks": checks}
