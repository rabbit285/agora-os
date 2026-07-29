from __future__ import annotations

import os
from collections.abc import AsyncIterator

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.db.register_all_models  # noqa: F401 — registers every model's table
from app.core.rbac import ensure_system_roles
from app.db.base import Base
from app.db.session import get_db
from app.integrations.workflow_client import get_sync_starter
from app.knowledge.workflow_client import get_ingestion_starter
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

    async def _noop_ingestion_starter():  # type: ignore[no-untyped-def]
        async def _start(document_id: object) -> None:
            # Tests never have a real Temporal server; ingestion itself is
            # tested directly against app.knowledge.service.ingest_document
            # (see tests/test_knowledge.py), not through the workflow.
            return None

        return _start

    async def _noop_sync_starter():  # type: ignore[no-untyped-def]
        async def _start(connection_id: object, sync_run_id: object) -> None:
            # Tests never have a real Temporal server; sync execution is
            # tested directly against app.integrations.service.execute_sync_run
            # (see tests/test_integrations.py), not through the workflow.
            return None

        return _start

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_ingestion_starter] = _noop_ingestion_starter
    app.dependency_overrides[get_sync_starter] = _noop_sync_starter
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_roles(db_session: AsyncSession) -> None:
    await ensure_system_roles(db_session)
