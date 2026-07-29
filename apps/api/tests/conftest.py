from __future__ import annotations

import os
from collections.abc import AsyncIterator

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai import models as ai_models  # noqa: F401
from app.audit import models as audit_models  # noqa: F401
from app.core import models as core_models  # noqa: F401
from app.core.rbac import ensure_system_roles
from app.db.base import Base
from app.db.session import get_db
from app.identity import models as identity_models  # noqa: F401
from app.main import app

engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _setup_db() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_roles(db_session: AsyncSession) -> None:
    await ensure_system_roles(db_session)
