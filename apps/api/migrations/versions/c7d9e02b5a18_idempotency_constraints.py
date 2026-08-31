"""Logical identity for the records the pipeline could duplicate.

Reprocessing a document was an append, not a reconciliation: five runs
over one policy left five Evidence rows for the same file and control,
and the control's evidence count was counting our retries rather than
the customer's documents.

Three identities are declared here as partial unique indexes, and the
existing duplicates are collapsed first — a constraint cannot be added
over data that violates it.

Partial, in every case, because the columns are nullable for good
reasons: uploads are presigned so a file's content hash is unknown until
the pipeline first reads the bytes, and rows written before this
migration have no hash at all. `WHERE ... IS NOT NULL` lets that history
stand while binding everything written from now on.

Collapsing keeps the **oldest** row of each group and repoints anything
referencing the others at it. Oldest rather than newest deliberately:
the first row is the one a person may already have approved, linked to,
or cited, and the later ones are the accidents.

Revision ID: c7d9e02b5a18
Revises: a1d5c93b7e40
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7d9e02b5a18"
down_revision = "a1d5c93b7e40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- new identity columns -----------------------------------------
    op.add_column("files", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_files_content_hash", "files", ["content_hash"])

    op.add_column(
        "evidence_suggestions", sa.Column("passage_hash", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "ix_evidence_suggestions_passage_hash", "evidence_suggestions", ["passage_hash"]
    )

    op.add_column(
        "notifications", sa.Column("idempotency_key", sa.String(length=200), nullable=True)
    )

    # --- collapse the duplicates that already exist -------------------
    #
    # Evidence: one document supporting one control is one piece of
    # evidence. Suggestions pointing at a discarded row are repointed at
    # the survivor first, so no approval decision is orphaned.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY organization_id, file_id, control_id
                       ORDER BY created_at, id
                   ) AS keep_id
            FROM evidence
            WHERE control_id IS NOT NULL
        )
        UPDATE evidence_suggestions AS s
        SET evidence_id = ranked.keep_id
        FROM ranked
        WHERE s.evidence_id = ranked.id AND ranked.id <> ranked.keep_id
        """
    )
    op.execute(
        """
        DELETE FROM evidence AS e
        USING (
            SELECT id,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY organization_id, file_id, control_id
                       ORDER BY created_at, id
                   ) AS keep_id
            FROM evidence
            WHERE control_id IS NOT NULL
        ) AS ranked
        WHERE e.id = ranked.id AND ranked.id <> ranked.keep_id
        """
    )

    # Suggestions: one passage of one document against one control.
    # Backfilled from the columns the identity is made of, so existing
    # rows join the constraint rather than sitting outside it forever.
    op.execute(
        """
        UPDATE evidence_suggestions
        SET passage_hash = encode(
            sha256(
                convert_to(
                    lower(regexp_replace(coalesce(source_location, ''), '\\s+', ' ', 'g'))
                    || chr(31)
                    || lower(regexp_replace(coalesce(quoted_passage, ''), '\\s+', ' ', 'g')),
                    'UTF8'
                )
            ),
            'hex'
        )
        WHERE passage_hash IS NULL
        """
    )
    # An approved suggestion outranks a proposed one when collapsing: a
    # human decision is the thing least safe to discard.
    op.execute(
        """
        DELETE FROM evidence_suggestions AS s
        USING (
            SELECT id,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY organization_id, file_id, control_id, passage_hash
                       ORDER BY
                           CASE status
                               WHEN 'approved' THEN 0
                               WHEN 'auto_approved' THEN 1
                               WHEN 'rejected' THEN 2
                               WHEN 'proposed' THEN 3
                               ELSE 4
                           END,
                           created_at,
                           id
                   ) AS keep_id
            FROM evidence_suggestions
            WHERE passage_hash IS NOT NULL
        ) AS ranked
        WHERE s.id = ranked.id AND ranked.id <> ranked.keep_id
        """
    )

    # --- the constraints ----------------------------------------------
    op.create_index(
        "uq_evidence_org_file_control",
        "evidence",
        ["organization_id", "file_id", "control_id"],
        unique=True,
        postgresql_where=sa.text("control_id IS NOT NULL"),
    )
    op.create_index(
        "uq_suggestion_identity",
        "evidence_suggestions",
        ["organization_id", "file_id", "control_id", "passage_hash"],
        unique=True,
        postgresql_where=sa.text("passage_hash IS NOT NULL"),
    )
    op.create_index(
        "uq_file_org_content_hash",
        "files",
        ["organization_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )
    op.create_index(
        "uq_notification_idempotency",
        "notifications",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    # One open gap per deficiency. Resolved gaps are excluded so a
    # requirement that genuinely regresses can raise a new one, with the
    # old one preserved as history.
    op.create_index(
        "uq_gap_open_identity",
        "compliance_gaps",
        ["organization_id", "requirement_id", "control_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )


def downgrade() -> None:
    op.drop_index("uq_gap_open_identity", table_name="compliance_gaps")
    op.drop_index("uq_notification_idempotency", table_name="notifications")
    op.drop_index("uq_file_org_content_hash", table_name="files")
    op.drop_index("uq_suggestion_identity", table_name="evidence_suggestions")
    op.drop_index("uq_evidence_org_file_control", table_name="evidence")
    op.drop_column("notifications", "idempotency_key")
    op.drop_index("ix_evidence_suggestions_passage_hash", table_name="evidence_suggestions")
    op.drop_column("evidence_suggestions", "passage_hash")
    op.drop_index("ix_files_content_hash", table_name="files")
    op.drop_column("files", "content_hash")
