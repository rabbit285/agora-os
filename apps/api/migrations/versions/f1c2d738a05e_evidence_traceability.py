"""Evidence traceability: where a passage came from, and why it routed

Revision ID: f1c2d738a05e
Revises: e8b30f2a94c1
Create Date: 2026-08-18

An evidence mapping an auditor cannot follow back to a place in a
document is a claim, not evidence. `source_location` records where the
quoted passage sits, `evidence_type` distinguishes a policy statement
from a record showing something happened, and `routing_reason` explains
after the fact why a suggestion was auto-approved or sent to a human.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1c2d738a05e"
down_revision = "e8b30f2a94c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_suggestions",
        sa.Column("source_location", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "evidence_suggestions",
        sa.Column("evidence_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "evidence_suggestions",
        sa.Column("requirement_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence_suggestions",
        sa.Column("routing_reason", sa.String(length=300), nullable=True),
    )
    op.create_foreign_key(
        "fk_evidence_suggestions_requirement",
        "evidence_suggestions",
        "requirements",
        ["requirement_id"],
        ["id"],
    )
    op.create_index(
        "ix_evidence_suggestions_requirement_id",
        "evidence_suggestions",
        ["requirement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evidence_suggestions_requirement_id", table_name="evidence_suggestions"
    )
    op.drop_constraint(
        "fk_evidence_suggestions_requirement", "evidence_suggestions", type_="foreignkey"
    )
    op.drop_column("evidence_suggestions", "routing_reason")
    op.drop_column("evidence_suggestions", "requirement_id")
    op.drop_column("evidence_suggestions", "evidence_type")
    op.drop_column("evidence_suggestions", "source_location")
