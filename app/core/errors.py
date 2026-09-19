"""Consistent error handling: custom exceptions and the error envelope.

All API errors return: {"error": {"code": "...", "message": "...", "details": ...}}
This is enforced by the exception handlers registered in main.py.
"""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error with a machine-readable code."""

    def __init__(self, code: str, message: str, status_code: int = 400, details: Any = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str = "Resource", details: Any = None):
        super().__init__("NOT_FOUND", f"{resource} not found", 404, details)


class ConflictError(AppError):
    def __init__(self, message: str = "Resource already exists", details: Any = None):
        super().__init__("CONFLICT", message, 409, details)


class ForbiddenError(AppError):
    """Raised but returned as 404 to avoid leaking resource existence."""

    def __init__(self):
        super().__init__("NOT_FOUND", "Resource not found", 404)


class ValidationError(AppError):
    def __init__(self, message: str, details: Any = None):
        super().__init__("VALIDATION_ERROR", message, 422, details)


class RateLimitError(AppError):
    def __init__(self):
        super().__init__("RATE_LIMITED", "Too many requests, please try again later", 429)


class FileTooLargeError(AppError):
    def __init__(self, max_mb: int):
        super().__init__("FILE_TOO_LARGE", f"File exceeds {max_mb}MB limit", 413)


class UnsupportedMediaError(AppError):
    def __init__(self, mime: str):
        super().__init__("UNSUPPORTED_MEDIA", f"Unsupported file type: {mime}", 415)


def error_envelope(code: str, message: str, details: Any = None) -> dict:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(exc.code, exc.message, exc.details),
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope("HTTP_ERROR", str(exc.detail)),
    )


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Format FastAPI schema/query validation errors in the standard error envelope."""
    return JSONResponse(
        status_code=422,
        content=error_envelope("VALIDATION_ERROR", "Request validation failed", exc.errors()),
    )


import logging

logger = logging.getLogger("app.core.errors")


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: never leak stack traces to clients, but log them."""
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=error_envelope("INTERNAL_ERROR", "An unexpected error occurred"),
    )
