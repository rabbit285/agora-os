"""Record who audited, and whether they are one of ours.

`auditor_name` was free text, so an internal audit run by a colleague
carried a string where it could have carried an identity — and the audit
trail could not say who, only what somebody typed. External auditors are
still a name, because that is genuinely all we have; the point is that
the two cases are now distinguishable rather than flattened into one.

Revision ID: c9e5b204f7a3
Revises: b6f1d38ac927
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9e5b204f7a3"
down_revision = "b6f1d38ac927"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audits",
        sa.Column(
            "auditor_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    # Existing rows keep their text and gain no user. Matching names to
    # accounts would be guessing which colleague somebody meant, and a
    # wrong actor in an audit trail is worse than an honest blank.


def downgrade() -> None:
    op.drop_column("audits", "auditor_user_id")
