"""DPIA quality gates: special-category decision, section provenance

The lifecycle was right and the content was not. A DPIA could complete
carrying Veyntra's own prompt where its argument belonged — "State why
this processing is necessary" approved as the necessity assessment — on
a rationale of "ok", while reporting "no personal-data categories are
recorded" for a medical-leave activity.

This adds what the content gates need to be recorded rather than
inferred:

* the special-category decision. Veyntra detects health signals in a
  processing record; whether Article 9 data is in scope is a person's
  answer, and "nobody has answered" must stay distinguishable from
  "confirmed not applicable, for this reason".
* `quality_review_reason`, so a DPIA already completed on weak content
  can be flagged without rewriting the snapshot it froze. History is not
  edited to match a rule introduced afterwards.

Section approvals gain provenance in the existing `section_reviews`
JSON rather than new columns: the digest of the processing the text was
approved against, so a later change to the ROPA can mark the sign-off
stale instead of silently keeping it.

Revision ID: f7a3b91d2e64
Revises: e6c2a84f1b39
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f7a3b91d2e64"
down_revision = "e6c2a84f1b39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dpias", sa.Column("special_category_confirmed", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "dpias",
        sa.Column("special_category_rationale", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "dpias", sa.Column("special_category_decided_by", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_dpias_special_category_decided_by_users",
        "dpias",
        "users",
        ["special_category_decided_by"],
        ["id"],
    )
    op.add_column(
        "dpias",
        sa.Column("special_category_decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dpias", sa.Column("quality_review_reason", sa.String(length=2000), nullable=True)
    )

    # An activity already marked as holding special-category data is an
    # answer somebody gave when they accepted the ROPA entry, so the DPIA
    # inherits it rather than re-asking. The decider is left null: it was
    # recorded on the activity, and attributing it to a guessed actor
    # would be a fabricated audit trail.
    op.execute(
        """
        UPDATE dpias
           SET special_category_confirmed = true
         WHERE processing_activity_id IN (
                   SELECT id FROM processing_activities
                    WHERE special_category IS true
               )
        """
    )


def downgrade() -> None:
    op.drop_column("dpias", "quality_review_reason")
    op.drop_column("dpias", "special_category_decided_at")
    op.drop_constraint(
        "fk_dpias_special_category_decided_by_users", "dpias", type_="foreignkey"
    )
    op.drop_column("dpias", "special_category_decided_by")
    op.drop_column("dpias", "special_category_rationale")
    op.drop_column("dpias", "special_category_confirmed")
