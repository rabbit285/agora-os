"""A duplicate upload points at the document it duplicates.

The row is kept rather than deleted: somebody did upload a file, and
making it disappear would be a lie about what happened. It simply stops
being a second document — no second set of evidence, gaps or tasks for
one real-world policy.

Revision ID: d3f8b91c7e25
Revises: c7d9e02b5a18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d3f8b91c7e25"
down_revision = "c7d9e02b5a18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("files", sa.Column("duplicate_of_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_files_duplicate_of", "files", "files", ["duplicate_of_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_files_duplicate_of", "files", type_="foreignkey")
    op.drop_column("files", "duplicate_of_id")
