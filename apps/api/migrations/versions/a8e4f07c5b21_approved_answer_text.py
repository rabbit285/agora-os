"""Record the words an answer was approved with.

"Has this answer changed since it was approved?" is the question a
customer-facing export has to ask before quoting an answer as approved,
and it turns out not to be answerable from timestamps. `updated_at` moves
on the same flush that records the approval — so comparing it against
`approved_at` flags every freshly approved answer as changed. It was
caught by a preview reporting "3 answers have changed since approval"
over three answers approved seconds earlier in one request.

Comparing the current text against the text that was signed off is the
only truthful answer, so the text that was signed off has to be kept.

Existing approved answers are backfilled from their current text. As of
this migration they are, by definition, unchanged since approval; the
alternative is raising a discrepancy on every historical answer at once,
which nobody could act on and which would not be true. Answers that were
never approved keep a null, and null means "we cannot tell" — the export
treats that as unchanged rather than inventing a problem.

Revision ID: a8e4f07c5b21
Revises: f1a63d28b904
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8e4f07c5b21"
down_revision = "f1a63d28b904"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questionnaire_answers",
        sa.Column("approved_text", sa.String(length=4000), nullable=True),
    )
    op.execute(
        "UPDATE questionnaire_answers SET approved_text = answer_text "
        "WHERE status = 'approved'"
    )


def downgrade() -> None:
    op.drop_column("questionnaire_answers", "approved_text")
