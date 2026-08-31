"""Privacy records get governance, and data requests get a real deadline

Three changes the privacy workspace needs before it can be a worklist
rather than four forms.

**Data request deadlines were thirty days.** The response window is one
month from receipt, and those are different dates for most of the year.
A request received on 31 January is due on 28 February; adding thirty
days answers on 2 March, two days past the deadline, with the product's
own screen saying the request is on time. Receipt also becomes its own
column: the clock runs from when the request arrived, not from when
somebody got around to logging it. Existing rows are backfilled from
`created_at`, which is the best evidence of receipt we have for them,
and their deadlines are recomputed on that basis.

**Processing activities get a review cadence.** A RoPA entry is a claim
an organization keeps making about itself, and one nobody has confirmed
in two years is a different thing from one reviewed last month.

**Transfers get a vendor link and a review date.** Adequacy decisions get
struck down and SCCs get superseded, so "we recorded SCCs once" is not
the same claim as "this transfer is covered".

Revision ID: f3c91d5a86b2
Revises: e2b8c46f9a71
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3c91d5a86b2"
down_revision = "e2b8c46f9a71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- processing activities ------------------------------------------
    op.add_column(
        "processing_activities",
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "processing_activities",
        sa.Column(
            "last_reviewed_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "processing_activities",
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "processing_activities",
        sa.Column(
            "special_category",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "processing_activities",
        sa.Column("special_category_condition", sa.String(length=60), nullable=True),
    )

    # --- data requests ---------------------------------------------------
    op.add_column(
        "dsars",
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dsars",
        sa.Column(
            "extension_months", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "dsars", sa.Column("extension_reason", sa.String(length=1000), nullable=True)
    )
    op.add_column(
        "dsars",
        sa.Column("extension_granted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Receipt is when the request arrived. For rows that predate the
    # column, when it was logged is the best evidence of that we have.
    op.execute(
        sa.text("UPDATE dsars SET received_at = created_at WHERE received_at IS NULL")
    )
    op.alter_column("dsars", "received_at", nullable=False)

    # And the deadline is recomputed on the correct basis. Postgres does
    # the calendar arithmetic and clamps a short month for us — 31 Jan +
    # 1 month is 28 Feb, which is exactly the behaviour that was missing.
    op.execute(
        sa.text(
            """
            UPDATE dsars
               SET due_at = received_at + INTERVAL '1 month'
             WHERE fulfilled_at IS NULL
            """
        )
    )

    # --- transfers --------------------------------------------------------
    op.add_column(
        "data_transfers",
        sa.Column(
            "vendor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("vendors.id"), nullable=True
        ),
    )
    op.create_index(
        "ix_data_transfers_vendor_id", "data_transfers", ["vendor_id"]
    )
    op.add_column(
        "data_transfers",
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "data_transfers",
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("data_transfers", "next_review_at")
    op.drop_column("data_transfers", "last_reviewed_at")
    op.drop_index("ix_data_transfers_vendor_id", table_name="data_transfers")
    op.drop_column("data_transfers", "vendor_id")
    op.drop_column("dsars", "extension_granted_at")
    op.drop_column("dsars", "extension_reason")
    op.drop_column("dsars", "extension_months")
    op.drop_column("dsars", "received_at")
    op.drop_column("processing_activities", "special_category_condition")
    op.drop_column("processing_activities", "special_category")
    op.drop_column("processing_activities", "next_review_at")
    op.drop_column("processing_activities", "last_reviewed_by")
    op.drop_column("processing_activities", "last_reviewed_at")
