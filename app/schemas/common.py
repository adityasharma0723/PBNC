"""Common schema components used across the API."""

from typing import Any
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    """Consistent error envelope used by all error responses."""
    error: ErrorDetail

    model_config = {"json_schema_extra": {
        "example": {"error": {"code": "NOT_FOUND", "message": "Resource not found"}}
    }}


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20
