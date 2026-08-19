"""AI system governance facts

Revision ID: a2f7d61b3c85
Revises: f1c2d738a05e
Create Date: 2026-08-18

An AI inventory that records a name and a vendor cannot answer the
questions the EU AI Act actually asks: who is affected, is there human
oversight, does it make automated decisions about people, is it in
production. These are declared facts rather than inferred ones, and how
many are missing is what `documentation_completeness` reports.

All default to the answer that keeps obligations narrow, so an incomplete
entry never manufactures a finding.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a2f7d61b3c85"
down_revision = "f1c2d738a05e"
branch_labels = None
depends_on = None

_BOOLS = (
    "is_external",
    "personal_data_processed",
    "sensitive_data_processed",
    "automated_decision_making",
)


def upgrade() -> None:
    for column in _BOOLS:
        op.add_column(
            "ai_systems",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.add_column("ai_systems", sa.Column("geography", sa.String(length=200), nullable=True))
    op.add_column(
        "ai_systems", sa.Column("human_oversight", sa.String(length=2000), nullable=True)
    )
    op.add_column(
        "ai_systems",
        sa.Column(
            "deployment_status",
            sa.String(length=20),
            nullable=False,
            server_default="development",
        ),
    )
    op.add_column(
        "ai_systems",
        sa.Column("third_party_vendors", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("ai_systems", "third_party_vendors")
    op.drop_column("ai_systems", "deployment_status")
    op.drop_column("ai_systems", "human_oversight")
    op.drop_column("ai_systems", "geography")
    for column in reversed(_BOOLS):
        op.drop_column("ai_systems", column)
