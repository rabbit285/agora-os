"""Privacy records that draft themselves from what is already recorded

The privacy module knew nothing about the rest of the product. An
organization that had already declared an AI system's purpose, the
people it affects, the data it processes and the vendor behind it still
had to type all of that again into a RoPA form, and again into a
transfer form.

Three things make that unnecessary.

**Vendors get a location.** Transfer detection is impossible without it:
"is this a third-country transfer" is a question about where the
processor is, and the product had nowhere to record that.

**Processing activities link to AI systems and vendors.** Join tables
rather than columns, because both sides are plural in practice and the
link has to be navigable from either end.

**Proposals get their own table.** A RoPA assembled from inference is
not the statement an organization makes to a regulator, so suggestions
live apart from records, and the unique key on their logical identity
means analysing the same AI system twice reconciles rather than
duplicating.

Revision ID: a4e17c8b02d9
Revises: f3c91d5a86b2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a4e17c8b02d9"
down_revision = "f3c91d5a86b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- where a processor actually is ----------------------------------
    op.add_column("vendors", sa.Column("country", sa.String(length=2), nullable=True))
    op.add_column(
        "vendors", sa.Column("data_location", sa.String(length=300), nullable=True)
    )

    # --- the cross-links -------------------------------------------------
    op.create_table(
        "processing_activity_ai_systems",
        sa.Column(
            "processing_activity_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("processing_activities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "ai_system_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("ai_systems.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "processing_activity_vendors",
        sa.Column(
            "processing_activity_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("processing_activities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "vendor_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("vendors.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # --- proposals, kept apart from records ------------------------------
    op.create_table(
        "privacy_suggestions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("source_key", sa.String(length=200), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="proposed"
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSON(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSON(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("created_record_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "decided_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # One proposal per thing proposed, however many times the records
        # are analysed. This is what makes re-analysis idempotent rather
        # than merely usually-idempotent.
        sa.UniqueConstraint(
            "organization_id",
            "kind",
            "source_key",
            name="uq_privacy_suggestion_identity",
        ),
    )
    op.create_index(
        "ix_privacy_suggestions_organization_id",
        "privacy_suggestions",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_privacy_suggestions_organization_id", table_name="privacy_suggestions"
    )
    op.drop_table("privacy_suggestions")
    op.drop_table("processing_activity_vendors")
    op.drop_table("processing_activity_ai_systems")
    op.drop_column("vendors", "data_location")
    op.drop_column("vendors", "country")
