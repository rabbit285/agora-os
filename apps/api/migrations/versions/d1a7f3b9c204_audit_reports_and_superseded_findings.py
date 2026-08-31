"""Audit reports, and findings that were replaced rather than duplicated

Two things a completed audit was missing.

`audit_reports` is the issued report: written once, never edited, one row
per generated version. A preview writes nothing here — the record is of
reports issued, not reports considered.

The `superseded_*` columns on `audit_findings` name something that was
already happening and had no vocabulary. When an auditor verified and
closed an observation and then changed their conclusion on that same
requirement, a second finding was raised — correctly, because reopening
a signed verification would rewrite somebody's signature — and the first
was left in the list with nothing marking it as replaced. That is why a
completed ISO 42001 audit read "18 conclusions, 19 findings".

The backfill marks those already in the data. It changes no severity, no
status and no verification: it records a relationship that is already
derivable from `audit_items.finding_id` pointing somewhere else.

Revision ID: d1a7f3b9c204
Revises: c9e5b204f7a3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d1a7f3b9c204"
down_revision = "c9e5b204f7a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_reports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "audit_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("audits.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "file_format", sa.String(length=10), nullable=False, server_default="pdf"
        ),
        sa.Column(
            "file_id", sa.Uuid(as_uuid=True), sa.ForeignKey("files.id"), nullable=True
        ),
        sa.Column(
            "contents",
            postgresql.JSON(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("source_digest", sa.String(length=64), nullable=True),
        sa.Column(
            "generated_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("audit_id", "version", name="uq_audit_report_version"),
    )
    op.create_index(
        "ix_audit_reports_organization_id", "audit_reports", ["organization_id"]
    )
    op.create_index("ix_audit_reports_audit_id", "audit_reports", ["audit_id"])

    op.add_column(
        "audit_findings",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audit_findings",
        sa.Column(
            "superseded_by_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("audit_findings.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_findings",
        sa.Column("superseded_reason", sa.String(length=300), nullable=True),
    )

    # A finding raised from an audit row whose row now points at a
    # different finding was replaced. Nothing else about it changes: the
    # severity it was raised at, the status it reached and the
    # verification somebody signed all stand.
    op.execute(
        sa.text(
            """
            UPDATE audit_findings AS f
               SET superseded_at = COALESCE(replacement.created_at, f.updated_at),
                   superseded_by_id = replacement.id,
                   superseded_reason = 'Replaced by a later conclusion on the same requirement.'
              FROM audit_items AS i
              JOIN audit_findings AS replacement ON replacement.id = i.finding_id
             WHERE f.audit_item_id = i.id
               AND i.finding_id IS NOT NULL
               AND i.finding_id <> f.id
               AND f.superseded_at IS NULL
            """
        )
    )

    # The other shape of the same thing: the auditor changed their
    # conclusion to one that raises no finding at all, so the row points
    # at nothing and the closed finding was left dangling.
    op.execute(
        sa.text(
            """
            UPDATE audit_findings AS f
               SET superseded_at = f.updated_at,
                   superseded_reason = 'Replaced by a later conclusion on the same requirement.'
              FROM audit_items AS i
             WHERE f.audit_item_id = i.id
               AND i.finding_id IS NULL
               AND f.superseded_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("audit_findings", "superseded_reason")
    op.drop_column("audit_findings", "superseded_by_id")
    op.drop_column("audit_findings", "superseded_at")
    op.drop_index("ix_audit_reports_audit_id", table_name="audit_reports")
    op.drop_index("ix_audit_reports_organization_id", table_name="audit_reports")
    op.drop_table("audit_reports")
