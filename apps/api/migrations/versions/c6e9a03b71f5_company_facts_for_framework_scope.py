"""Company facts that determine which frameworks are in scope

Revision ID: c6e9a03b71f5
Revises: a7d4e21b93f6
Create Date: 2026-08-18

The customer cannot answer "which frameworks apply to us" on their own —
that is the question the product exists to answer. Answering it needs
facts about the company, and those facts have to be declared rather than
inferred so every recommendation is traceable to something the
organization actually said.

All flags default false: an unanswered question must never manufacture a
regulatory obligation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c6e9a03b71f5"
down_revision = "a7d4e21b93f6"
branch_labels = None
depends_on = None

_BOOLEAN_FACTS = (
    "operates_in_eu",
    "sells_to_eu_customers",
    "processes_personal_data",
    "processes_special_category_data",
    "uses_third_party_ai",
    "builds_ai_features",
    "is_data_processor",
    "sells_to_enterprise",
)


def upgrade() -> None:
    for column in _BOOLEAN_FACTS:
        op.add_column(
            "onboarding_profiles",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.add_column(
        "onboarding_profiles", sa.Column("sector", sa.String(length=60), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("onboarding_profiles", "sector")
    for column in reversed(_BOOLEAN_FACTS):
        op.drop_column("onboarding_profiles", column)
