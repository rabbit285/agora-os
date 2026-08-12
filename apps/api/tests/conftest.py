from __future__ import annotations

import os
from collections.abc import AsyncIterator

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("APP_ENV", "test")

# Third-party provider credentials are force-cleared, not `setdefault`-ed:
# a developer with real keys in their environment (or a container started
# from infra/docker/.env) would otherwise have the suite silently switch
# from the deterministic demo adapters to live providers. That has already
# broken this suite twice — once when APOLLO_API_KEY was present, making
# the "returns demo-labeled results" tests hit Apollo and fail on a plan
# restriction, and again when a real OPENAI_API_KEY turned the AI tests
# into live calls that failed on the account's quota. Tests must not
# depend on, or spend, anyone's real credentials.
#
# Must happen before `app.config` is first imported below, since Settings
# reads the environment once at module import.
os.environ["AI_PROVIDER"] = "demo"
for _provider_key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "APOLLO_API_KEY", "CLEARBIT_API_KEY"):
    os.environ.pop(_provider_key, None)
# app.core.rate_limit's real per-IP limit is production-tuned; the full
# suite issues thousands of requests from one loopback identity, which
# would otherwise trip it. test_rate_limit.py monkeypatches this setting
# back down to prove real enforcement.
os.environ.setdefault("RATE_LIMIT_MAX_REQUESTS_PER_MINUTE", "1000000")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.db.register_all_models  # noqa: F401 — registers every model's table
from app.automation.workflow_client import (
    get_run_signaler,
    get_run_starter,
    get_schedule_deleter,
    get_schedule_syncer,
)
from app.core.rbac import ensure_system_roles
from app.db.base import Base
from app.db.session import get_db
from app.integrations.workflow_client import get_sync_starter
from app.knowledge.workflow_client import get_ingestion_starter
from app.main import app
from app.sales.workflow_client import get_enrichment_starter, get_import_starter

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

    async def _noop_run_starter():  # type: ignore[no-untyped-def]
        async def _start(run_id: object) -> None:
            # Tests never have a real Temporal server; run execution is
            # tested directly against app.automation.service.advance_run
            # (see tests/test_automation_service.py), not through the
            # workflow.
            return None

        return _start

    async def _noop_run_signaler():  # type: ignore[no-untyped-def]
        async def _signal(run_id: object) -> None:
            return None

        return _signal

    async def _noop_schedule_syncer():  # type: ignore[no-untyped-def]
        async def _sync(workflow_id: object, cron: object) -> None:
            return None

        return _sync

    async def _noop_schedule_deleter():  # type: ignore[no-untyped-def]
        async def _delete(workflow_id: object) -> None:
            return None

        return _delete

    async def _noop_enrichment_starter():  # type: ignore[no-untyped-def]
        async def _start(job_id: object) -> None:
            # Tests never have a real Temporal server; enrichment execution
            # is tested directly against
            # app.sales.enrichment_job_service.execute_enrichment_job (see
            # tests/test_sales_lead_finder.py), not through the workflow.
            return None

        return _start

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_ingestion_starter] = _noop_ingestion_starter
    app.dependency_overrides[get_sync_starter] = _noop_sync_starter
    app.dependency_overrides[get_run_starter] = _noop_run_starter
    app.dependency_overrides[get_run_signaler] = _noop_run_signaler
    app.dependency_overrides[get_schedule_syncer] = _noop_schedule_syncer
    app.dependency_overrides[get_schedule_deleter] = _noop_schedule_deleter
    async def _noop_import_starter():  # type: ignore[no-untyped-def]
        async def _start(job_id: object) -> None:
            # Tests never have a real Temporal server; import execution is
            # tested directly against
            # app.sales.import_job_service.execute_import_job (see
            # tests/test_sales_lead_finder.py), not through the workflow.
            return None

        return _start

    app.dependency_overrides[get_enrichment_starter] = _noop_enrichment_starter
    app.dependency_overrides[get_import_starter] = _noop_import_starter
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_roles(db_session: AsyncSession) -> None:
    await ensure_system_roles(db_session)
