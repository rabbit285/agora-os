"""The date a document says it takes effect.

Detected already — `detect_effective_date` has been reading it since
version detection was added — but never kept, so the screen that asks
somebody to confirm a version relationship could show them the version
numbers and not the dates. Comparing "Version 1.0, effective May 2026"
with "Version 2.0, effective August 2026" is most of how a person decides
whether one replaces the other.

Stored as text, exactly as the document writes it. "August 2026" is what
the policy says; turning that into 2026-08-01 would put a day in the
document's mouth that nobody wrote — the same promise
`detect_version_label` makes about version numbers.

Revision ID: e2c46b81af73
Revises: d9b2e50f16a4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2c46b81af73"
down_revision = "d9b2e50f16a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("version_effective_date", sa.String(length=60), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("files", "version_effective_date")
