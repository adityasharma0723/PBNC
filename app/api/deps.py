"""FastAPI dependencies: DB session, current user extraction, rate limiting.

Security note: get_current_user extracts the user_id from the JWT and
verifies the user exists. All downstream queries filter by owner_id.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_async_session
from app.models.user import User


async def get_db(session: AsyncSession = Depends(get_async_session)) -> AsyncSession:  # type: ignore[misc]
    yield session


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("UNAUTHORIZED", "Missing or invalid Authorization header", 401)

    token = authorization[7:]
    user_id = decode_access_token(token)
    if user_id is None:
        raise AppError("UNAUTHORIZED", "Invalid or expired token", 401)

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise AppError("UNAUTHORIZED", "Invalid token payload", 401)

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError("UNAUTHORIZED", "User not found", 401)

    return user
