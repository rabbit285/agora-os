"""Evidence events: the receiving end of continuous monitoring

Revision ID: b9c5e14d7a30
Revises: a2f7d61b3c85
Create Date: 2026-08-18

Compliance decays. A control that passed in March fails in June because
someone turned off branch protection, and nobody finds out until the next
audit. An evidence event is a connector's observation that the position
may have moved — it flags the control for reassessment and lets the
deterministic assessment decide, rather than grading the control itself.

Append-only: a connector reporting a change must never be able to destroy
the record of what was true before.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b9c5e14d7a30"
down_revision = "a2f7d61b3c85"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column(
            "control_id", sa.Uuid(as_uuid=True), sa.ForeignKey("controls.id"), nullable=True
        ),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "triggered_reassessment", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_events_organization_id", "evidence_events", ["organization_id"])
    op.create_index("ix_evidence_events_source", "evidence_events", ["source"])
    op.create_index("ix_evidence_events_control_id", "evidence_events", ["control_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_events_control_id", table_name="evidence_events")
    op.drop_index("ix_evidence_events_source", table_name="evidence_events")
    op.drop_index("ix_evidence_events_organization_id", table_name="evidence_events")
    op.drop_table("evidence_events")
