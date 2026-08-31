"""One logical document, many versions.

Policies already had lineage — `policy_versions` has recorded superseded
documents since governance was added. Everything else did not: a revised
DPIA, a new sub-processor list or an updated procedure arrived as an
unrelated document, and the library grew a second row that competed with
the first for the same evidence.

The chain lives on `files` rather than in a new table because a version
*is* an upload; the only thing missing was which upload it replaced.
Superseded rows keep all their evidence and stay readable — an auditor
asking what a policy said last March needs the row, not a tombstone.

Revision ID: b6e4f92a1c37
Revises: a4c8e15b9d72
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b6e4f92a1c37"
down_revision = "a4c8e15b9d72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("files", sa.Column("supersedes_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("files", sa.Column("superseded_by_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("files", sa.Column("version_label", sa.String(length=40), nullable=True))
    op.create_index("ix_files_superseded_by_id", "files", ["superseded_by_id"])
    op.create_foreign_key(
        "fk_files_supersedes", "files", "files", ["supersedes_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_files_superseded_by", "files", "files", ["superseded_by_id"], ["id"]
    )

    # A document can only supersede one other, and can only be superseded
    # once. Without this a retried "use as new version" could fork the
    # chain into two heads, and "which version is current" would stop
    # having one answer.
    op.create_index(
        "uq_files_supersedes",
        "files",
        ["supersedes_id"],
        unique=True,
        postgresql_where=sa.text("supersedes_id IS NOT NULL"),
        sqlite_where=sa.text("supersedes_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_files_supersedes", table_name="files")
    op.drop_constraint("fk_files_superseded_by", "files", type_="foreignkey")
    op.drop_constraint("fk_files_supersedes", "files", type_="foreignkey")
    op.drop_index("ix_files_superseded_by_id", table_name="files")
    op.drop_column("files", "version_label")
    op.drop_column("files", "superseded_by_id")
    op.drop_column("files", "supersedes_id")
