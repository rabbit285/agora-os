"""Audit-specific scope exclusions.

Scope is the auditor's to set, and a requirement that binds the
organization can still be outside the scope of one engagement. Until now
the only way to keep something out of an audit was to change the
organization's framework applicability — which answers a different
question, and quietly rewrites what the company is held to in order to
shape one report.

Revision ID: b6f1d38ac927
Revises: a8e4f07c5b21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b6f1d38ac927"
down_revision = "a8e4f07c5b21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_items",
        sa.Column("excluded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audit_items",
        sa.Column(
            "excluded_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.add_column(
        "audit_items",
        sa.Column("exclusion_reason", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    for column in ("exclusion_reason", "excluded_by", "excluded_at"):
        op.drop_column("audit_items", column)
