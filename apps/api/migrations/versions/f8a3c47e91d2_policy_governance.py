"""Policy governance: ownership, approval, versions, review cycles

Revision ID: f8a3c47e91d2
Revises: e7b2419fd35c
Create Date: 2026-08-24

A `Policy` was a title, a file reference and a two-state flag. That is not
governance — the questions an auditor asks are who owns it, which version
is in force, who approved it and when it is next reviewed, and none of
those had anywhere to live.

`policy_versions` is append-only. A superseded document is never deleted:
"what did your retention policy say in March" is a real question, and a
product that overwrote the file cannot answer it.

Existing rows keep working. `published` maps onto `approved`, and `draft`
onto `needs_review` — the same two states, named for what they mean in a
governance lifecycle rather than for a publish button.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f8a3c47e91d2"
down_revision = "e7b2419fd35c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "policies",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.add_column("policies", sa.Column("category", sa.String(length=120), nullable=True))
    op.add_column("policies", sa.Column("version", sa.String(length=40), nullable=True))
    op.add_column(
        "policies",
        sa.Column("approved_by", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "policies", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "policies", sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "policies", sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "policies", sa.Column("review_frequency_months", sa.Integer(), nullable=True)
    )
    op.add_column(
        "policies",
        sa.Column(
            "detected_automatically",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_foreign_key(
        "fk_policies_approved_by_users", "policies", "users", ["approved_by"], ["id"]
    )

    # The old vocabulary, mapped rather than dropped.
    op.execute("UPDATE policies SET status = 'approved' WHERE status = 'published'")
    op.execute("UPDATE policies SET status = 'needs_review' WHERE status = 'draft'")

    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "policy_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("policies.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "file_id", sa.Uuid(as_uuid=True), sa.ForeignKey("files.id"), nullable=False
        ),
        sa.Column("version", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="current"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("policy_versions")
    op.drop_constraint("fk_policies_approved_by_users", "policies", type_="foreignkey")
    for column in (
        "detected_automatically",
        "review_frequency_months",
        "next_review_at",
        "effective_date",
        "approved_at",
        "approved_by",
        "version",
        "category",
    ):
        op.drop_column("policies", column)
    op.execute("UPDATE policies SET status = 'published' WHERE status = 'approved'")
    op.execute("UPDATE policies SET status = 'draft' WHERE status <> 'published'")
    op.alter_column(
        "policies",
        "status",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
