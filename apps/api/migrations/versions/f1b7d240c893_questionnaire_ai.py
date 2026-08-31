"""Questionnaire answers that say what they need from a person.

`missing` described the row being empty rather than what the reader has
to do about it, and the screen printed it verbatim. The status model now
separates "nobody has looked" from "Veyntra drafted something and needs a
decision", and carries the confidence and the reason alongside.

Existing rows migrate by meaning: an empty `missing` row is `unanswered`;
one that somehow held text is a `draft`.

Revision ID: f1b7d240c893
Revises: e5a1c93d7f60
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1b7d240c893"
down_revision = "e5a1c93d7f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questionnaires", sa.Column("customer_name", sa.String(length=200), nullable=True)
    )
    op.add_column(
        "questionnaires", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column("questionnaire_answers", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(
        "questionnaire_answers", sa.Column("review_reason", sa.String(length=600), nullable=True)
    )
    op.add_column(
        "questionnaire_answers", sa.Column("approved_by", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.add_column(
        "questionnaire_answers",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_questionnaire_answers_approved_by",
        "questionnaire_answers",
        "users",
        ["approved_by"],
        ["id"],
    )

    op.execute(
        """
        UPDATE questionnaire_answers
        SET status = CASE
            WHEN answer_text IS NULL OR btrim(answer_text) = '' THEN 'unanswered'
            WHEN status = 'missing' THEN 'draft'
            ELSE status
        END
        """
    )
    op.alter_column("questionnaire_answers", "status", server_default="unanswered")


def downgrade() -> None:
    op.execute(
        "UPDATE questionnaire_answers SET status = 'missing' "
        "WHERE status IN ('unanswered', 'needs_review', 'rejected')"
    )
    op.alter_column("questionnaire_answers", "status", server_default="missing")
    op.drop_constraint(
        "fk_questionnaire_answers_approved_by", "questionnaire_answers", type_="foreignkey"
    )
    op.drop_column("questionnaire_answers", "approved_at")
    op.drop_column("questionnaire_answers", "approved_by")
    op.drop_column("questionnaire_answers", "review_reason")
    op.drop_column("questionnaire_answers", "confidence")
    op.drop_column("questionnaires", "due_at")
    op.drop_column("questionnaires", "customer_name")
