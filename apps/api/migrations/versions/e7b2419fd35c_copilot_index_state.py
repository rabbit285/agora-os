"""Whether a document is retrievable by the Copilot

Revision ID: e7b2419fd35c
Revises: d41e7a06c8b2
Create Date: 2026-08-22

Document Intelligence and Copilot indexing were two pipelines that never
met: uploading a compliance document parsed it, extracted evidence and
mapped it to controls, but never chunked or embedded it. The Copilot
searches `document_chunks`, so it answered "I don't have any indexed
documents" for an organization with eighteen processed files.

`processing_status` could not carry this. It says Document Intelligence
finished, which is a different question from whether the Copilot can
retrieve the text — and a document can pass the first and fail the
second when an embedding call errors.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7b2419fd35c"
down_revision = "d41e7a06c8b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column(
            "index_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("files", sa.Column("index_error", sa.Text(), nullable=True))
    op.add_column(
        "files",
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_files_index_status", "files", ["index_status"])


def downgrade() -> None:
    op.drop_index("ix_files_index_status", table_name="files")
    op.drop_column("files", "indexed_at")
    op.drop_column("files", "index_error")
    op.drop_column("files", "index_status")
