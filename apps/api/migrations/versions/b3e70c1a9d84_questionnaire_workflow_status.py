"""A questionnaire status that says what the answers say.

`Questionnaire.status` was a column nothing maintained. It was set to
`draft` at creation and then only ever moved by somebody pressing a
button, while the detail screen computed its own progress from the
answers and reported "Ready to share". A questionnaire with every answer
approved sat in the list marked `Draft` indefinitely, and both screens
were telling the truth as they understood it.

Two changes here, both data:

- `in_progress` becomes `in_review`. The old name described that work was
  happening; the new one describes what is *needed* — a person to decide
  — which is the thing a reader has to act on.
- Every questionnaire is recalculated from its own answers, so the rows
  that went stale while nothing maintained them are corrected in place.

`ready_to_share` is new and is only ever reached by that calculation.
`completed` is left alone: it means the questionnaire went back to the
customer, which no amount of reading the answers can tell us.

Archive state is untouched. Where a record lives and how far its work got
are different questions, and this migration answers only the second.

Revision ID: b3e70c1a9d84
Revises: a7d3f92e64c1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3e70c1a9d84"
down_revision = "a7d3f92e64c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # The rename first, so the recalculation below compares against the
    # vocabulary it is about to write.
    renamed = connection.execute(
        sa.text("UPDATE questionnaires SET status = 'in_review' WHERE status = 'in_progress'")
    ).rowcount

    # One row per questionnaire with the counts that decide its status.
    # A question with no answer row counts as unanswered, which is
    # exactly the case that keeps a questionnaire in draft — an inner
    # join here would hide it and call the questionnaire ready.
    rows = connection.execute(
        sa.text(
            """
            SELECT q.id,
                   q.status,
                   COUNT(qq.id) AS questions,
                   COUNT(*) FILTER (
                       WHERE COALESCE(qa.status, 'unanswered')
                             IN ('unanswered', 'draft', 'rejected')
                   ) AS unfinished,
                   COUNT(*) FILTER (WHERE qa.status = 'needs_review') AS needs_review
            FROM questionnaires q
            LEFT JOIN questionnaire_questions qq ON qq.questionnaire_id = q.id
            LEFT JOIN questionnaire_answers qa ON qa.question_id = qq.id
            GROUP BY q.id, q.status
            """
        )
    ).all()

    corrected = 0
    for row in rows:
        if not row.questions:
            expected = "draft"
        elif row.unfinished:
            expected = "draft"
        elif row.needs_review:
            expected = "in_review"
        elif row.status == "completed":
            # It went to the customer. Reading the answers cannot unsay
            # that, and nothing here should.
            expected = "completed"
        else:
            expected = "ready_to_share"

        if expected != row.status:
            connection.execute(
                sa.text("UPDATE questionnaires SET status = :status WHERE id = :id"),
                {"status": expected, "id": row.id},
            )
            corrected += 1

    print(
        f"questionnaire status backfill: {renamed} renamed from in_progress, "
        f"{corrected} stale row(s) corrected"
    )


def downgrade() -> None:
    # The new states have no old equivalent. `ready_to_share` was work in
    # progress under the old vocabulary; `in_review` is where it came
    # from. Nothing recovers which rows were stale before the upgrade,
    # and pretending otherwise would be worse than saying so.
    op.execute(
        "UPDATE questionnaires SET status = 'in_progress' "
        "WHERE status IN ('in_review', 'ready_to_share')"
    )
