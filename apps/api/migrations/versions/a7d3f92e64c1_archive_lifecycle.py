"""Archived, for questionnaires and audits.

People need to clear test records and duplicates out of a working list.
They must not be able to clear away an answer somebody approved or a
finding an auditor raised — so the untidy-list problem gets its own
answer, and deletion stays reserved for records nothing has happened to.

A timestamp rather than a status value. Archiving is orthogonal to how
far the work got: a completed questionnaire that is archived is still
completed, and restoring it has to put it back exactly as it was.
Folding "archived" into `status` would overwrite the answer to "how far
did this get" with the answer to "is this on the active list", and the
first is not recoverable afterwards.

Indexed because every active list filters on it.

Revision ID: a7d3f92e64c1
Revises: f4a91d6c05be
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7d3f92e64c1"
down_revision = "f4a91d6c05be"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("questionnaires", "audits"):
        op.add_column(
            table,
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table, sa.Column("archived_by", sa.Uuid(as_uuid=True), nullable=True)
        )
        op.create_index(f"ix_{table}_archived_at", table, ["archived_at"])
        op.create_foreign_key(
            f"fk_{table}_archived_by", table, "users", ["archived_by"], ["id"]
        )


def downgrade() -> None:
    for table in ("questionnaires", "audits"):
        op.drop_constraint(f"fk_{table}_archived_by", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_archived_at", table_name=table)
        op.drop_column(table, "archived_by")
        op.drop_column(table, "archived_at")
