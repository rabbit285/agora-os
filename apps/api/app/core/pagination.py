"""Generic pagination (spec §E7 "API Quality": "pagination; sorting").
Additive query parameters: a caller that never passes `limit`/`offset`
gets exactly the same response shape every list endpoint already
returns (a bare JSON array of every matching row) — nothing changes for
the many existing frontend callers. Passing them applies a real SQL
LIMIT/OFFSET and the true total row count is reported via an
`X-Total-Count` response header rather than by wrapping the body, for
the same backward-compatibility reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


@dataclass
class Pagination:
    limit: int | None
    offset: int


def pagination_params(
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


async def paginate(
    db: AsyncSession, stmt: Select[Any], pagination: Pagination, response: Response
) -> list[Any]:
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    response.headers["X-Total-Count"] = str(total)
    if pagination.limit is not None:
        stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
