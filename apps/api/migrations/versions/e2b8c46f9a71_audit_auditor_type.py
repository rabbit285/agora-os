"""Auditor type recorded, and legacy auditors reconciled to their accounts

The reported bug: a completed audit whose auditor is a colleague printed
"Zach Warren (external)" in the formal report. Nothing had recorded that
he was external — the report inferred it, from `auditor_user_id IS NULL`.

That column only started being written when the create form gained an
auditor picker. Every audit before it stored the auditor as text, so the
inference labelled every legacy audit's auditor external, including all
the internal ones. Internal-vs-external is a fact about organization
membership; it is not derivable from whether an account happened to be
linked at creation.

So it becomes a column, and this backfills what can be established
safely:

- an audit that already links a user is internal, by definition
- an audit whose auditor name matches exactly one member of that same
  organization is internal, and gets the link

Anything else is left null. A name matching two members, or none, is not
evidence of anything — least of all that the person was external — and
guessing would put a wrong identity in a document people rely on. Those
rows read as unresolved until somebody says which they are.

Revision ID: e2b8c46f9a71
Revises: d1a7f3b9c204
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2b8c46f9a71"
down_revision = "d1a7f3b9c204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audits", sa.Column("auditor_type", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "audits",
        sa.Column("auditor_organization", sa.String(length=300), nullable=True),
    )

    # A linked account is a member of the organization by construction.
    op.execute(
        sa.text(
            """
            UPDATE audits
               SET auditor_type = 'internal'
             WHERE auditor_user_id IS NOT NULL
               AND auditor_type IS NULL
            """
        )
    )

    # A name that matches exactly one member of the same organization.
    # The count guard is the whole safety of this: two Zach Warrens in
    # one tenant means neither is matched, because picking one would
    # attribute an audit to a person who did not conduct it.
    op.execute(
        sa.text(
            """
            UPDATE audits AS a
               SET auditor_user_id = matched.user_id,
                   auditor_type = 'internal'
              FROM (
                    SELECT m.organization_id,
                           lower(btrim(u.full_name)) AS name_key,
                           -- Only ever read when `matches = 1`, so which
                           -- element this picks is not a choice. There is
                           -- no min() for uuid in Postgres.
                           (array_agg(u.id))[1] AS user_id,
                           count(*) AS matches
                      FROM memberships m
                      JOIN users u ON u.id = m.user_id
                     WHERE u.full_name IS NOT NULL
                       AND btrim(u.full_name) <> ''
                     GROUP BY m.organization_id, lower(btrim(u.full_name))
                   ) AS matched
             WHERE a.auditor_user_id IS NULL
               AND a.auditor_type IS NULL
               AND a.auditor_name IS NOT NULL
               AND matched.matches = 1
               AND matched.organization_id = a.organization_id
               AND matched.name_key = lower(btrim(a.auditor_name))
            """
        )
    )


def downgrade() -> None:
    op.drop_column("audits", "auditor_organization")
    op.drop_column("audits", "auditor_type")
