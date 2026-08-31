"""Running the same operation twice and getting one record.

Distinct from `app.core.idempotency`, which replays an HTTP response for
a client that retried a request. This is the layer underneath: the same
*work* running twice — a background job retrying, a queue redelivering,
a document being reprocessed — must converge on one logical record, even
when no client and no header are involved.

The pipeline is full of operations that legitimately run more than once,
and every one of them was an append. Reprocessing one policy five times
left five Evidence rows for the same file and control, so the control's
evidence count was counting our retries.

Two things are needed, and neither is sufficient alone.

**A logical identity.** What makes two records the same compliance fact
rather than the same row — a file's content rather than its name, an
evidence mapping's (document, control) pair rather than its primary key.
Identity is declared per entity, on the model it belongs to.

**A safe way to act on it.** `if not exists: insert` is not one. Two
workers can both pass the check and both insert; the window is small, and
retries are exactly when it is widest, because that is when duplicate
work is concurrent by definition. So the insert is attempted against a
database uniqueness constraint and the conflict is *expected*: whoever
loses the race reads back the winner's row.

The constraint is the guarantee. This module is the ergonomics.
"""

from __future__ import annotations

import hashlib
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


def content_fingerprint(data: bytes) -> str:
    """The identity of a file: what is in it, not what it is called.

    SHA-256 of the bytes. Two uploads of the same document under
    different filenames are the same document, and a rename does not
    create a new one.
    """
    return hashlib.sha256(data).hexdigest()


def text_fingerprint(*parts: str | None) -> str:
    """A stable identity for a passage of text.

    Whitespace and case are normalized first, so a re-extraction that
    rewraps a paragraph does not read as a different quotation. Parts are
    joined with a separator that cannot occur in normalized text, so
    ("ab", "c") and ("a", "bc") cannot collide.
    """
    normalized = "\x1f".join(" ".join((part or "").split()).lower() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def get_or_create(
    db: AsyncSession,
    model: type[T],
    *,
    match: dict[str, Any],
    defaults: dict[str, Any] | None = None,
) -> tuple[T, bool]:
    """Return the row identified by `match`, creating it if absent.

    Safe under concurrency, which a read-then-insert is not: the insert
    carries ON CONFLICT DO NOTHING, so if another transaction created the
    same logical row first, this one inserts nothing and reads theirs
    back. Both callers end up with the same record and neither raises.

    Returns `(row, created)`. `created` is False when the row already
    existed — callers use it to decide whether this is a real state
    transition worth announcing, or a retry that should stay quiet.

    Requires a unique constraint covering `match`. Without one the
    conflict never fires and this degrades to read-then-insert, which is
    why every identity it is used for has an index behind it.
    """
    existing = await _find(db, model, match)
    if existing is not None:
        return (existing, False)

    table = model.__table__  # type: ignore[attr-defined]
    values = {**match, **(defaults or {})}

    try:
        statement = (
            pg_insert(table).values(**values).on_conflict_do_nothing().returning(table.c.id)
        )
        inserted = (await db.execute(statement)).scalar_one_or_none()
    except (NotImplementedError, AttributeError, IntegrityError):
        # The test suite runs on SQLite, which has no ON CONFLICT support
        # through this dialect. Falling back to the ORM keeps the tests
        # meaningful for the *logic*; the concurrency guarantee is the
        # Postgres index, and is asserted separately against Postgres.
        return await _orm_fallback(db, model, values, match)

    if inserted is None:
        # Lost the race. The winner's row is the answer — re-read it
        # rather than reporting a failure for an operation that
        # succeeded, just not in this transaction.
        await db.flush()
        row = await _find(db, model, match)
        if row is None:  # pragma: no cover - conflict on a different index
            raise RuntimeError(
                f"{model.__name__} insert conflicted on a constraint other than its identity"
            )
        return (row, False)

    await db.flush()
    row = await db.get(model, inserted)
    assert row is not None
    return (row, True)


async def _orm_fallback(
    db: AsyncSession, model: type[T], values: dict[str, Any], match: dict[str, Any]
) -> tuple[T, bool]:
    row = model(**values)  # type: ignore[operator]
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = await _find(db, model, match)
        if existing is None:  # pragma: no cover
            raise
        return (existing, False)
    return (row, True)


async def _find(db: AsyncSession, model: type[T], match: dict[str, Any]) -> T | None:
    conditions = [getattr(model, column) == value for column, value in match.items()]
    return (await db.execute(select(model).where(*conditions))).scalars().first()


__all__ = ["content_fingerprint", "get_or_create", "text_fingerprint"]
