"""A proposed version relationship, before anyone accepts it.

Detection and linking are deliberately separate columns. Veyntra can be
confident that an upload is the next version of a document and still be
wrong, and a link made on that confidence would move evidence between
documents with nobody having agreed to it.

Revision ID: c8f1a7d34e02
Revises: b6e4f92a1c37
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8f1a7d34e02"
down_revision = "b6e4f92a1c37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files", sa.Column("version_candidate_id", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.add_column(
        "files", sa.Column("version_confidence", sa.String(length=10), nullable=True)
    )
    op.create_foreign_key(
        "fk_files_version_candidate", "files", "files", ["version_candidate_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_files_version_candidate", "files", type_="foreignkey")
    op.drop_column("files", "version_confidence")
    op.drop_column("files", "version_candidate_id")
