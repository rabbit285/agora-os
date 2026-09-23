"""DSAR workflow: reviewable scope, per-source discovery, approved response

Three tables and six columns behind one change of shape: a data request
stops being a record somebody fills in and becomes a case the product
works, with a person deciding the parts that need judgement.

The tables carry the decisions that must survive a re-run. Scope
inclusion, review decisions and an approved package all belong to a
person, and every one of them would be lost if these lived in the
discovery findings blob that each run overwrites.

Revision ID: b3e8f2a71c94
Revises: a9d4c17e35b2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b3e8f2a71c94"
down_revision = "a9d4c17e35b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dsars", sa.Column("verification_notes", sa.String(2000), nullable=True))
    # Backfilled to "received" for every existing row, then made
    # non-null. Deriving the real phase here would mean running the
    # workflow rules inside a migration; the application recomputes it on
    # the next read of each request, which is both correct and cheaper.
    op.add_column(
        "dsars",
        sa.Column("phase", sa.String(30), nullable=False, server_default="received"),
    )
    op.add_column("dsars", sa.Column("blocked_reason", sa.String(1000), nullable=True))
    op.add_column(
        "dsars", sa.Column("scope_confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "dsars",
        sa.Column(
            "scope_confirmed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    op.create_table(
        "dsar_scope_sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "dsar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dsars.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("source_key", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("relevance", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("relevance_reason", sa.String(600), nullable=True),
        sa.Column("linked_systems", sa.JSON(), nullable=True),
        sa.Column("connected", sa.Boolean(), nullable=False, server_default=sa.false()),
        # Nullable on purpose: "nobody has decided" is not "excluded".
        sa.Column("included", sa.Boolean(), nullable=True),
        sa.Column("added_by_user", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("dsar_id", "source_key", name="uq_dsar_scope_source_key"),
    )

    op.create_table(
        "dsar_discovered_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "dsar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dsars.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("source_key", sa.String(200), nullable=False),
        sa.Column("source_name", sa.String(300), nullable=False),
        sa.Column("search_state", sa.String(30), nullable=False),
        sa.Column("matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("record_ids", sa.JSON(), nullable=True),
        sa.Column("state_detail", sa.String(1000), nullable=True),
        sa.Column(
            "review_decision", sa.String(20), nullable=False, server_default="needs_review"
        ),
        sa.Column("review_reason", sa.String(1000), nullable=True),
        sa.Column(
            "reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sensitivity_flags", sa.JSON(), nullable=True),
        sa.Column(
            "task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("dsar_id", "source_key", name="uq_dsar_discovered_source_key"),
    )

    op.create_table(
        "dsar_response_packages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "dsar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dsars.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("contents", sa.JSON(), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column(
            "approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("files.id"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("dsar_response_packages")
    op.drop_table("dsar_discovered_items")
    op.drop_table("dsar_scope_sources")
    op.drop_column("dsars", "scope_confirmed_by")
    op.drop_column("dsars", "scope_confirmed_at")
    op.drop_column("dsars", "blocked_reason")
    op.drop_column("dsars", "phase")
    op.drop_column("dsars", "verification_notes")
