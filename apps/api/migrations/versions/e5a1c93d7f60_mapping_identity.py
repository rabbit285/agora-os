"""An evidence mapping is identified by document and control, not by quote.

The first attempt keyed a suggestion on the passage the model quoted.
That is stable only as far as the model is: re-extraction phrases the
same citation slightly differently, hashes differently, and reads as a
new proposal — two concurrent deliveries of the same job produced two
extra mappings for one document and one control.

The spec's identity is the right one: *the same evidence → control
mapping must exist only once*. A document either evidences a control or
it does not, and which sentence the model chose to quote this time is an
attribute of that mapping rather than what makes it distinct. It is still
stored, and refreshed on reprocessing, so a changed quote is visible.

Revision ID: e5a1c93d7f60
Revises: d3f8b91c7e25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5a1c93d7f60"
down_revision = "d3f8b91c7e25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_suggestion_identity", table_name="evidence_suggestions")

    # Collapse to one mapping per (organization, document, control). A
    # human decision outranks a proposal: the verdict is the thing least
    # safe to discard.
    op.execute(
        """
        DELETE FROM evidence_suggestions AS s
        USING (
            SELECT id,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY organization_id, file_id, control_id
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
        ) AS ranked
        WHERE s.id = ranked.id AND ranked.id <> ranked.keep_id
        """
    )

    op.create_index(
        "uq_suggestion_document_control",
        "evidence_suggestions",
        ["organization_id", "file_id", "control_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_suggestion_document_control", table_name="evidence_suggestions")
    op.create_index(
        "uq_suggestion_identity",
        "evidence_suggestions",
        ["organization_id", "file_id", "control_id", "passage_hash"],
        unique=True,
        postgresql_where=sa.text("passage_hash IS NOT NULL"),
    )
