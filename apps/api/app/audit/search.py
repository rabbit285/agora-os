"""Searching the audit trail by the name of the thing that changed.

An audit event stores a UUID, not a name. So "what happened to the AI
Governance Policy" cannot be answered by searching `audit_events` at
all — the string is not in the table.

The names are resolved first, here: every record whose name matches the
term is looked up in its own table, and the trail is then filtered to
those ids. Doing it the other way round — fetching a page of events and
filtering after resolution — silently searches only the rows that
happened to load, which is worse than not searching, because it looks
like it worked.

Tenant-scoped throughout: only this organization's records can turn into
ids to filter on, so a name search can never surface another
organization's history.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    DPIA,
    AIIncident,
    AISystem,
    ComplianceGap,
    Control,
    Framework,
    Policy,
    Vendor,
)
from app.core.models import File, Task
from app.identity.models import User

# Enough to answer a real question, capped so one broad term ("a")
# cannot turn into an unbounded IN clause.
MATCHES_PER_TYPE = 50


async def matching_object_ids(
    db: AsyncSession, *, organization_id: uuid.UUID, term: str
) -> list[str]:
    """Ids of this organization's records whose name matches `term`.

    Frameworks are catalog data and are not organization-scoped, so they
    are matched globally — an event referencing one is still scoped by
    the audit query itself.
    """
    pattern = f"%{term.strip()}%"
    if not term.strip():
        return []

    found: list[str] = []

    async def collect(model, columns, *, scoped: bool = True) -> None:
        conditions = [cast(getattr(model, column), String).ilike(pattern) for column in columns]
        stmt = select(model.id).where(or_(*conditions))
        if scoped:
            stmt = stmt.where(model.organization_id == organization_id)
        rows = (await db.execute(stmt.limit(MATCHES_PER_TYPE))).scalars().all()
        found.extend(str(row) for row in rows)

    await collect(Control, ("title", "description"))
    await collect(Policy, ("title",))
    await collect(File, ("original_filename",))
    await collect(AISystem, ("name", "purpose"))
    await collect(AIIncident, ("title",))
    await collect(Task, ("title",))
    await collect(ComplianceGap, ("summary", "recommendation"))
    await collect(Vendor, ("name",))
    await collect(DPIA, ("title",))
    await collect(Framework, ("name", "key"), scoped=False)

    # People, so "who did what" can be searched by name as well as read.
    # Users are matched through their membership of this organization.
    users = (
        (
            await db.execute(
                select(User.id)
                .where(
                    or_(
                        cast(User.full_name, String).ilike(pattern),
                        cast(User.email, String).ilike(pattern),
                    )
                )
                .limit(MATCHES_PER_TYPE)
            )
        )
        .scalars()
        .all()
    )
    found.extend(str(user_id) for user_id in users)

    return found


__all__ = ["MATCHES_PER_TYPE", "matching_object_ids"]
