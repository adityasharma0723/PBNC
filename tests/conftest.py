"""Pytest configuration and fixtures.

Uses an in-memory approach with test database and httpx async client.
All tests run OFFLINE using the FakeExtractor.
"""

import os
import uuid
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["EXTRACTOR"] = "fake"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["DATABASE_URL_SYNC"] = "sqlite://"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["UPLOAD_DIR"] = os.path.join(os.path.dirname(__file__), "test_uploads")

from app.db.base import Base
from app.main import app
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.core.security import hash_password, create_access_token
from app.workers.celery_app import celery_app

celery_app.conf.update(
    task_always_eager=True,
    broker_url="memory://",
    result_backend="cache+memory://",
)

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def async_engine_fixture():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(async_engine_fixture) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(
        async_engine_fixture, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        password_hash=hash_password("testpassword123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    """A second user for isolation tests."""
    user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        password_hash=hash_password("otherpassword123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def client(db_session: AsyncSession, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    token = create_access_token(str(test_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac

    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def other_client(db_session: AsyncSession, other_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as the other user for isolation tests."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    token = create_access_token(str(other_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac

    app.dependency_overrides.clear()

@pytest.fixture
def upload_dir(tmp_path):
    """Create a temporary upload directory."""
    upload = tmp_path / "uploads"
    upload.mkdir()
    os.environ["UPLOAD_DIR"] = str(upload)
    from app.core.config import settings
    settings.UPLOAD_DIR = str(upload)
    return str(upload)
