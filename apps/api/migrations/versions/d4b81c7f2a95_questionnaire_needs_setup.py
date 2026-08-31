"""Correct stored statuses for customer questionnaires with no customer.

Readiness stopped being a question only the answers could answer. A
customer-provided questionnaire is something we send back to a named
customer as part of their security review, so "ready to share" is a claim
about the engagement too: with no customer recorded and no review to
belong to, there is nobody to share it with.

Rows already in the database were written under the old rule, and several
of them sit at `ready_to_share` on the strength of their answers alone.
The status column is stored — that is what makes it queryable — so a rule
change has to reach the rows. Otherwise the list keeps showing "Ready to
share" over a record the API would now refuse to send anywhere, which is
the exact class of disagreement the stored status exists to prevent.

Only ever moves a row *into* `needs_setup`, and only where the new rule
says it belongs there:

    source = 'customer_provided'
    AND (customer_name IS NULL OR trim(customer_name) = ''
         OR security_review_id IS NULL)

Nothing else is touched. Answers, lifecycle, customers and links are all
left exactly as they are — this corrects a derived value, and derived
values are the only thing it is safe to correct in bulk.

Down restores each row to what the answers alone imply, which is what the
old rule would have produced. It cannot restore the exact prior string in
every case (a row that was `completed` before is not recoverable from the
answers), and that is the honest limit of reversing a rule change rather
than a data change.

Revision ID: d4b81c7f2a95
Revises: c5f28a6b0e13
"""

from __future__ import annotations

from alembic import op

revision = "d4b81c7f2a95"
down_revision = "c5f28a6b0e13"
branch_labels = None
depends_on = None


# A questionnaire that cannot be shared with anybody, whatever its
# answers say. Written once and used by both directions.
_UNSET_CUSTOMER = """
    source = 'customer_provided'
    AND (
        customer_name IS NULL
        OR trim(customer_name) = ''
        OR security_review_id IS NULL
    )
"""


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE questionnaires
        SET status = 'needs_setup'
        WHERE {_UNSET_CUSTOMER}
          AND status <> 'needs_setup'
        """
    )


def downgrade() -> None:
    # Back to what the answers alone say, which is what these rows would
    # have held under the old rule. `completed` is not recoverable — it
    # recorded that somebody sent the questionnaire, and nothing in the
    # answers remembers that.
    op.execute(
        f"""
        UPDATE questionnaires q
        SET status = CASE
            WHEN NOT EXISTS (
                SELECT 1 FROM questionnaire_questions qq
                WHERE qq.questionnaire_id = q.id
            ) THEN 'draft'
            WHEN EXISTS (
                SELECT 1 FROM questionnaire_questions qq
                LEFT JOIN questionnaire_answers qa ON qa.question_id = qq.id
                WHERE qq.questionnaire_id = q.id
                  AND (qa.status IS NULL
                       OR qa.status IN ('unanswered', 'draft', 'rejected'))
            ) THEN 'draft'
            WHEN EXISTS (
                SELECT 1 FROM questionnaire_questions qq
                JOIN questionnaire_answers qa ON qa.question_id = qq.id
                WHERE qq.questionnaire_id = q.id
                  AND qa.status = 'needs_review'
            ) THEN 'in_review'
            ELSE 'ready_to_share'
        END
        WHERE q.status = 'needs_setup'
        """
    )
