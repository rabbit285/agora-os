"""Resting state for files is not_analyzed, not uploaded

Revision ID: a7d4e21b93f6
Revises: f2b8e05c1d47
Create Date: 2026-08-17

Most files in an organization are attachments from other modules that
were never submitted for compliance analysis. Defaulting them to
`uploaded` made every one of them render as permanently mid-pipeline and
kept the document library polling for a run that was never started.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7d4e21b93f6"
down_revision = "f2b8e05c1d47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "files",
        "processing_status",
        server_default="not_analyzed",
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )
    # Anything still sitting at the old default was never actually
    # submitted for processing. Rows mid-pipeline or already finished are
    # left exactly as they are.
    op.execute(
        "UPDATE files SET processing_status = 'not_analyzed' "
        "WHERE processing_status = 'uploaded'"
    )


def downgrade() -> None:
    op.alter_column(
        "files",
        "processing_status",
        server_default="uploaded",
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE files SET processing_status = 'uploaded' "
        "WHERE processing_status = 'not_analyzed'"
    )
