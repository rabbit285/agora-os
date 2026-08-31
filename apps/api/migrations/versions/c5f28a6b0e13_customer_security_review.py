"""A customer security review that this product can actually create.

`security_reviews.opportunity_id` was a non-null foreign key into
`sales_opportunities`. That module was withdrawn, so the table became
impossible to write to — which is how the Assessments page came to show a
finished customer questionnaire beside "No customer security reviews".
There was nothing wrong with the link; there was no way to make one.

Three changes:

- `opportunity_id` and `questionnaire_id` become nullable. Existing rows
  keep both; nothing new sets either.
- The review gains a `title`, a `customer_name` and archive columns. The
  customer is a name, not a foreign key into a CRM this product does not
  have and is not getting back.
- `questionnaires.security_review_id` carries the link the other way, so
  one review holds many questionnaires — a customer sends a security
  questionnaire, then a privacy one, and they are one engagement.

The uniqueness index is what stops a retried import producing three
reviews for one customer. Partial on both counts: only active reviews
compete for a name, and a review with no customer named does not compete
at all.

Revision ID: c5f28a6b0e13
Revises: b3e70c1a9d84
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c5f28a6b0e13"
down_revision = "b3e70c1a9d84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "security_reviews", "opportunity_id", existing_type=sa.Uuid(), nullable=True
    )
    op.alter_column(
        "security_reviews", "questionnaire_id", existing_type=sa.Uuid(), nullable=True
    )

    op.add_column(
        "security_reviews", sa.Column("title", sa.String(length=300), nullable=True)
    )
    op.add_column(
        "security_reviews",
        sa.Column("customer_name", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "security_reviews",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "security_reviews", sa.Column("archived_by", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.create_index(
        "ix_security_reviews_customer_name", "security_reviews", ["customer_name"]
    )
    op.create_index(
        "ix_security_reviews_archived_at", "security_reviews", ["archived_at"]
    )
    op.create_foreign_key(
        "fk_security_reviews_archived_by",
        "security_reviews",
        "users",
        ["archived_by"],
        ["id"],
    )

    op.add_column(
        "questionnaires", sa.Column("security_review_id", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.create_index(
        "ix_questionnaires_security_review_id", "questionnaires", ["security_review_id"]
    )
    op.create_foreign_key(
        "fk_questionnaires_security_review",
        "questionnaires",
        "security_reviews",
        ["security_review_id"],
        ["id"],
    )

    # One active review per customer. Case-folded, because "Acme Corp"
    # and "acme corp" are one customer and creating a review for each is
    # exactly the duplicate this prevents.
    op.create_index(
        "uq_security_review_active_customer",
        "security_reviews",
        [sa.text("organization_id"), sa.text("lower(customer_name)")],
        unique=True,
        postgresql_where=sa.text("customer_name IS NOT NULL AND archived_at IS NULL"),
        sqlite_where=sa.text("customer_name IS NOT NULL AND archived_at IS NULL"),
    )

    # Existing reviews keep working: the legacy single link becomes the
    # new one, so a review created before this still shows its
    # questionnaire on the new relationship.
    op.execute(
        """
        UPDATE questionnaires
        SET security_review_id = sr.id
        FROM security_reviews sr
        WHERE sr.questionnaire_id = questionnaires.id
          AND questionnaires.security_review_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("uq_security_review_active_customer", table_name="security_reviews")
    op.drop_constraint(
        "fk_questionnaires_security_review", "questionnaires", type_="foreignkey"
    )
    op.drop_index("ix_questionnaires_security_review_id", table_name="questionnaires")
    op.drop_column("questionnaires", "security_review_id")

    op.drop_constraint(
        "fk_security_reviews_archived_by", "security_reviews", type_="foreignkey"
    )
    op.drop_index("ix_security_reviews_archived_at", table_name="security_reviews")
    op.drop_index("ix_security_reviews_customer_name", table_name="security_reviews")
    op.drop_column("security_reviews", "archived_by")
    op.drop_column("security_reviews", "archived_at")
    op.drop_column("security_reviews", "customer_name")
    op.drop_column("security_reviews", "title")

    # Rows created after the upgrade have no opportunity, so the column
    # cannot go back to NOT NULL without discarding them. Left nullable
    # deliberately rather than deleting a customer's reviews.
