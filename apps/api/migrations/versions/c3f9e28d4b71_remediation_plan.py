"""Structured remediation plan on a compliance gap

Revision ID: c3f9e28d4b71
Revises: b9c5e14d7a30
Create Date: 2026-08-20

A finding that says "attach the documents that demonstrate this control"
restates the gap and leaves the reader to work out what a complete answer
looks like — which is the expertise they came here for. The plan carries
the deficiency, why it is open, who usually owns the work, what evidence
would close it, and an ordered checklist.

Stored whole rather than as columns: it is written once, read once, and
every reader wants all of it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3f9e28d4b71"
down_revision = "b9c5e14d7a30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "compliance_gaps", sa.Column("remediation_plan", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("compliance_gaps", "remediation_plan")
