"""Customer-facing exports: disclosure state, source files, generated outputs.

Three things a product that sends documents outside the organization
needs and this one did not have.

**A disclosure state on every file.** There was no field anywhere saying
whether a document may leave. Any export feature built without one is a
feature that decides, on the customer's behalf, that everything is
shareable. The default here is `internal` — not because most documents
are sensitive, but because "nobody has classified this" and "nobody has
approved this for sharing" are the same answer, and the export path must
treat them the same way. `restricted` is stronger still: a vulnerability
report is not merely unclassified, and export refuses it outright.

**The questionnaire's source file.** A customer who sends a 42-row
spreadsheet wants those 42 rows back in their own columns. Keeping the
upload and the column mapping is what makes that possible; without it the
best available answer is a different document that happens to contain the
same answers.

**`review_exports`.** An immutable record of each package generated, with
the contents frozen at generation. When the review moves on afterwards,
the export stays as it was and the screen says so — because a customer's
copy and our record of what we sent them must not drift apart.

Revision ID: f1a63d28b904
Revises: e7c2a94b13d8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f1a63d28b904"
down_revision = "e7c2a94b13d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- who may see a document outside the organization --------------
    op.add_column(
        "files",
        sa.Column(
            "disclosure",
            sa.String(length=20),
            nullable=False,
            server_default="internal",
        ),
    )
    op.create_index("ix_files_disclosure", "files", ["disclosure"])

    # Everything already on file stays internal. Backfilling anything to
    # `customer_shareable` would be this migration deciding that
    # documents nobody has reviewed can be sent to customers, which is
    # exactly the decision it has no standing to make.

    # --- the questionnaire remembers where it came from ---------------
    op.add_column(
        "questionnaires",
        sa.Column(
            "source_file_id", sa.Uuid(as_uuid=True), sa.ForeignKey("files.id"), nullable=True
        ),
    )
    op.add_column(
        "questionnaires",
        sa.Column(
            "source_columns",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )

    # --- what was generated, and exactly what went into it ------------
    op.create_table(
        "review_exports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "security_review_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("security_reviews.id"),
            nullable=False,
        ),
        sa.Column("output_type", sa.String(length=30), nullable=False),
        sa.Column("file_format", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "file_id", sa.Uuid(as_uuid=True), sa.ForeignKey("files.id"), nullable=True
        ),
        sa.Column(
            "contents",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("source_digest", sa.String(length=64), nullable=True),
        sa.Column(
            "generated_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "shared_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_review_exports_organization_id", "review_exports", ["organization_id"]
    )
    op.create_index(
        "ix_review_exports_security_review_id", "review_exports", ["security_review_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_review_exports_security_review_id", table_name="review_exports")
    op.drop_index("ix_review_exports_organization_id", table_name="review_exports")
    op.drop_table("review_exports")
    op.drop_column("questionnaires", "source_columns")
    op.drop_column("questionnaires", "source_file_id")
    op.drop_index("ix_files_disclosure", table_name="files")
    op.drop_column("files", "disclosure")
