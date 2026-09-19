"""Async database session factory.

Design: one async engine shared across the app, sessions created per-request
via the FastAPI dependency in api/deps.py. Sync engine used only by Alembic
and Celery workers (which run in a sync context).
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Check database dialect
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
is_sync_sqlite = settings.DATABASE_URL_SYNC.startswith("sqlite")

from sqlalchemy.pool import StaticPool

async_kwargs = {"echo": settings.DEBUG}
if not is_sqlite:
    async_kwargs.update({"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20})
else:
    async_kwargs.update({"poolclass": StaticPool, "connect_args": {"check_same_thread": False}})

sync_kwargs = {"echo": settings.DEBUG}
if not is_sync_sqlite:
    sync_kwargs.update({"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10})
else:
    sync_kwargs.update({"poolclass": StaticPool, "connect_args": {"check_same_thread": False}})

# Async engine for FastAPI
async_engine = create_async_engine(
    settings.DATABASE_URL,
    **async_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine for Celery workers and Alembic
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    **sync_kwargs,
)

SyncSessionLocal = sessionmaker(
    sync_engine,
    class_=Session,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncSession:  # type: ignore[misc]
    async with AsyncSessionLocal() as session:
        yield session
