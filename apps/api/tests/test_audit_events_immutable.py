"""Regression test for the audit_events immutability trigger (spec §59,
finding A4 — migration `7f2a9c1d4e6b`). Proves the enforcement is real
DB-level behavior (a Postgres trigger), not just an application-code
convention: even a direct SQL `UPDATE`/`DELETE` against the table, issued
with the same role the application itself connects as, is rejected by the
database.

This suite runs against an in-memory SQLite database
(`tests/conftest.py`), which never runs Alembic migrations and doesn't
support Postgres triggers/PL/pgSQL — so these two tests are dialect-gated
and skip themselves on SQLite. The trigger is real and live-verified
directly against the running Postgres container instead (see
`docs/DECISIONS.md` ADR-0042); these tests exist so the behavior is also
covered automatically on any future CI matrix that points this suite at a
real Postgres database.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event


def _skip_unless_postgres(db_session: AsyncSession) -> None:
    if db_session.bind is None or db_session.bind.dialect.name != "postgresql":
        pytest.skip(
            "audit_events immutability trigger is Postgres-specific; this suite runs "
            "against SQLite (see module docstring) — verified live against Postgres instead"
        )


async def test_direct_update_against_an_audit_event_is_rejected_by_the_database(
    db_session: AsyncSession,
) -> None:
    _skip_unless_postgres(db_session)
    event = await record_event(
        db_session,
        organization_id=None,
        actor_user_id=None,
        action="test.immutability.probe",
        object_type="test",
        object_id=str(uuid.uuid4()),
    )
    await db_session.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(
            text("UPDATE audit_events SET action = 'tampered' WHERE id = :id"),
            {"id": event.id},
        )
    await db_session.rollback()


async def test_direct_delete_against_an_audit_event_is_rejected_by_the_database(
    db_session: AsyncSession,
) -> None:
    _skip_unless_postgres(db_session)
    event = await record_event(
        db_session,
        organization_id=None,
        actor_user_id=None,
        action="test.immutability.probe",
        object_type="test",
        object_id=str(uuid.uuid4()),
    )
    await db_session.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        await db_session.execute(
            text("DELETE FROM audit_events WHERE id = :id"), {"id": event.id}
        )
    await db_session.rollback()
