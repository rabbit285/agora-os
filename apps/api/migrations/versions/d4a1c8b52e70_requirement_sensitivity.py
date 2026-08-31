"""Requirement sensitivity, gating which evidence mappings need a human

Revision ID: d4a1c8b52e70
Revises: c6e9a03b71f5
Create Date: 2026-08-18

"high" marks requirements where a wrongly-accepted evidence mapping is
expensive to discover later — breach notification, DPIA, prohibited AI
practices, human oversight. Evidence proposed against those always
reaches a person, whatever confidence the model reported.

Defaults to "standard" so existing rows keep the previous behaviour until
the catalog seeder sets the real value.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4a1c8b52e70"
down_revision = "c6e9a03b71f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "requirements",
        sa.Column(
            "sensitivity",
            sa.String(length=20),
            nullable=False,
            server_default="standard",
        ),
    )


def downgrade() -> None:
    op.drop_column("requirements", "sensitivity")
