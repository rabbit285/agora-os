"""Files Veyntra produced, kept apart from files it was given

A generated report is a result of compliance work, not an independent
source of it. That distinction did not exist, so every report the
product wrote landed in the evidence library beside uploaded policies,
carrying "Not analyzed yet" and an "Analyze for evidence" button — and
one click closed a loop:

    evidence → assessment → audit → audit report → Documents →
    analyse → evidence → assessment …

The backfill is driven off the generation records themselves —
`audit_reports.file_id` and `review_exports.file_id` — which are
authoritative about what produced a file. Deliberately not off
filenames: a customer can upload something called "Audit Report v2",
and reclassifying that would quietly remove a real document from the
evidence library.

Nothing is deleted, and no file moves. Only how it is classified
changes, plus a processing status that stops the library offering to
analyse it.

Revision ID: b7d24e0f9c15
Revises: a4e17c8b02d9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7d24e0f9c15"
down_revision = "a4e17c8b02d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column(
            "artifact_type",
            sa.String(length=20),
            nullable=False,
            server_default="source",
        ),
    )
    op.add_column(
        "files", sa.Column("origin_type", sa.String(length=40), nullable=True)
    )
    op.add_column("files", sa.Column("origin_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column(
        "files", sa.Column("origin_label", sa.String(length=300), nullable=True)
    )
    op.create_index("ix_files_artifact_type", "files", ["artifact_type"])

    # --- audit reports ---------------------------------------------------
    op.execute(
        sa.text(
            """
            UPDATE files AS f
               SET artifact_type = 'generated_output',
                   origin_type = 'audit_report',
                   origin_id = r.audit_id,
                   origin_label = COALESCE(a.title, r.title),
                   processing_status = 'generated'
              FROM audit_reports AS r
              LEFT JOIN audits AS a ON a.id = r.audit_id
             WHERE r.file_id = f.id
               AND f.artifact_type = 'source'
            """
        )
    )

    # --- security review exports ------------------------------------------
    op.execute(
        sa.text(
            """
            UPDATE files AS f
               SET artifact_type = 'generated_output',
                   origin_type = 'review_export',
                   origin_id = e.security_review_id,
                   origin_label = COALESCE(s.title, e.title),
                   processing_status = 'generated'
              FROM review_exports AS e
              LEFT JOIN security_reviews AS s ON s.id = e.security_review_id
             WHERE e.file_id = f.id
               AND f.artifact_type = 'source'
            """
        )
    )


def downgrade() -> None:
    # The files themselves are untouched either way; only the
    # classification goes.
    op.execute(
        sa.text(
            "UPDATE files SET processing_status = 'not_analyzed' "
            "WHERE processing_status = 'generated'"
        )
    )
    op.drop_index("ix_files_artifact_type", table_name="files")
    op.drop_column("files", "origin_label")
    op.drop_column("files", "origin_id")
    op.drop_column("files", "origin_type")
    op.drop_column("files", "artifact_type")
