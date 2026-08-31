"""Document intelligence: processing lifecycle and classification on files

Revision ID: e1c7d94a2f3b
Revises: d9a3f17c5b82
Create Date: 2026-08-17

Gives every uploaded file a visible processing lifecycle so "upload once,
the AI does the compliance work" is observable rather than a claim: the
user watches a document move through parsing, classifying and analysing
instead of staring at a spinner with no idea whether anything happened.

`extracted_characters` exists so `ready` can never be asserted over an
empty extraction — a scanned PDF that yields no text would otherwise look
identical to a readable document that simply matched no controls.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1c7d94a2f3b"
down_revision = "d9a3f17c5b82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column(
            "processing_status",
            sa.String(length=20),
            nullable=False,
            server_default="uploaded",
        ),
    )
    op.add_column("files", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column(
        "files", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("files", sa.Column("extracted_characters", sa.Integer(), nullable=True))
    op.add_column("files", sa.Column("document_type", sa.String(length=80), nullable=True))
    op.add_column("files", sa.Column("document_domain", sa.String(length=80), nullable=True))
    op.create_index("ix_files_processing_status", "files", ["processing_status"])


def downgrade() -> None:
    op.drop_index("ix_files_processing_status", table_name="files")
    op.drop_column("files", "document_domain")
    op.drop_column("files", "document_type")
    op.drop_column("files", "extracted_characters")
    op.drop_column("files", "processed_at")
    op.drop_column("files", "processing_error")
    op.drop_column("files", "processing_status")
