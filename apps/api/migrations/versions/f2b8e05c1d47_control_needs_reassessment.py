"""Flag controls whose evidence changed since the last assessment

Revision ID: f2b8e05c1d47
Revises: e1c7d94a2f3b
Create Date: 2026-08-17

New evidence must not silently re-grade a control. The previous
assessment stays on the record and this flag marks it stale, so the user
is prompted to re-run rather than shown a number that quietly moved.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b8e05c1d47"
down_revision = "e1c7d94a2f3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "controls",
        sa.Column(
            "needs_reassessment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("controls", "needs_reassessment")
