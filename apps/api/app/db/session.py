from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _to_async_dsn(dsn: str) -> str:
    if dsn.startswith("postgresql+psycopg://"):
        return dsn.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


engine = create_async_engine(_to_async_dsn(settings.database_url), pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
