"""An evidence mapping is per requirement, not just per control.

The previous identity — (organization, document, control) — collapsed two
legitimately different mappings into one. A single policy can evidence
one control for Article 32 *and* for Article 33, and those are different
claims about different obligations: dropping the second cut the control's
coverage from 100% to 50%, because the requirement linkage lives on the
suggestion.

Two partial indexes rather than one, because `requirement_id` is
nullable and means something when it is null: the model named a control
without resolving which of its requirements the passage speaks to. That
is one mapping per (document, control), and the second index says so.

Revision ID: a4c8e15b9d72
Revises: f1b7d240c893
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a4c8e15b9d72"
down_revision = "f1b7d240c893"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_suggestion_document_control", table_name="evidence_suggestions")

    # Collapse only true duplicates under the wider identity. A human
    # decision outranks a proposal, as before.
    op.execute(
        """
        DELETE FROM evidence_suggestions AS s
        USING (
            SELECT id,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY organization_id, file_id, control_id, requirement_id
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
        "uq_suggestion_requirement",
        "evidence_suggestions",
        ["organization_id", "file_id", "control_id", "requirement_id"],
        unique=True,
        postgresql_where=sa.text("requirement_id IS NOT NULL"),
    )
    op.create_index(
        "uq_suggestion_control_only",
        "evidence_suggestions",
        ["organization_id", "file_id", "control_id"],
        unique=True,
        postgresql_where=sa.text("requirement_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_suggestion_control_only", table_name="evidence_suggestions")
    op.drop_index("uq_suggestion_requirement", table_name="evidence_suggestions")
    op.create_index(
        "uq_suggestion_document_control",
        "evidence_suggestions",
        ["organization_id", "file_id", "control_id"],
        unique=True,
    )
