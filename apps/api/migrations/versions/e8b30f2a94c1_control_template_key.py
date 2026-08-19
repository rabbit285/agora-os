"""Identify scaffolded controls so frameworks share them

Revision ID: e8b30f2a94c1
Revises: d4a1c8b52e70
Create Date: 2026-08-18

One measure satisfies requirements across several frameworks. Recording
which library template a control came from lets adopting a second
framework extend that control with new requirement mappings, instead of
creating a near-identical control in a different vocabulary and asking
the customer to evidence it twice.

Null for controls the organization wrote themselves — scaffolding never
touches those.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e8b30f2a94c1"
down_revision = "d4a1c8b52e70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "controls", sa.Column("template_key", sa.String(length=80), nullable=True)
    )
    op.create_index("ix_controls_template_key", "controls", ["template_key"])


def downgrade() -> None:
    op.drop_index("ix_controls_template_key", table_name="controls")
    op.drop_column("controls", "template_key")
