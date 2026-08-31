"""A version chain is a line, not a tree.

`accept_new_version` claimed a unique index stopped two concurrent
acceptances forking a chain. There wasn't one. The endpoint's guard —
"has this document already been superseded?" — is a read before a write,
so two people accepting two different uploads against the same previous
version both pass the check and both write: two files claiming to
supersede one version, and no answer to "which of these is current".

The database can simply refuse. Partial, because NULL is the normal
state — almost every file supersedes nothing and is superseded by
nothing.

Any chain already forked in existing data has to be settled before the
index can be built; the upgrade reports it rather than picking a winner,
because which upload a person meant to keep is not something a migration
can know.

Revision ID: f4a91d6c05be
Revises: e2c46b81af73
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4a91d6c05be"
down_revision = "e2c46b81af73"
branch_labels = None
depends_on = None


def _forks(connection, column: str) -> list[tuple[str, int]]:
    rows = connection.execute(
        sa.text(
            f"""
            SELECT {column}::text AS target, COUNT(*) AS n
            FROM files
            WHERE {column} IS NOT NULL
            GROUP BY {column}
            HAVING COUNT(*) > 1
            """  # noqa: S608 - column is one of two literals below
        )
    ).all()
    return [(row.target, row.n) for row in rows]


def upgrade() -> None:
    connection = op.get_bind()

    existing = _forks(connection, "supersedes_id") + _forks(connection, "superseded_by_id")
    if existing:
        detail = ", ".join(f"{target} ({count} rows)" for target, count in existing)
        raise RuntimeError(
            "Some version chains have already forked and must be settled by hand "
            "before this constraint can be added. Affected files: "
            f"{detail}. Decide which upload is the real next version, clear "
            "supersedes_id/superseded_by_id on the others, then re-run."
        )

    # The plain index on superseded_by_id is replaced by the unique one,
    # which serves the same lookups.
    op.drop_index("ix_files_superseded_by_id", table_name="files")
    op.create_index(
        "uq_file_supersedes",
        "files",
        ["supersedes_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_id IS NOT NULL"),
        sqlite_where=sa.text("supersedes_id IS NOT NULL"),
    )
    op.create_index(
        "uq_file_superseded_by",
        "files",
        ["superseded_by_id"],
        unique=True,
        postgresql_where=sa.text("superseded_by_id IS NOT NULL"),
        sqlite_where=sa.text("superseded_by_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_file_superseded_by", table_name="files")
    op.drop_index("uq_file_supersedes", table_name="files")
    op.create_index("ix_files_superseded_by_id", "files", ["superseded_by_id"])
