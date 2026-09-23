"""DPIA lifecycle: section review, consultation, completion, suggested risks

Screening, drafting and completion were three states the product talked
about but only partly stored. This adds what each of them needs to be a
record rather than an inference:

* `section_reviews` — which Article 35(7) sections a person signed off.
  Completion used to test whether the text still began with Veyntra's
  draft marker, so deleting one word counted as review and agreeing with
  a draft verbatim was impossible to express.
* consultation fields — Article 35(2) is a fact about something that did
  or did not happen. Null means unresolved; "no consultation performed"
  is an answer somebody gave.
* completion + snapshot — a finished DPIA is a statement about what was
  assessed then, so it is frozen instead of re-derived.
* `dpia_risk_suggestions` — proposals that are not yet risks, keyed by
  what they are about so re-analysis reconciles instead of duplicating.
* three `risks` columns Article 35(7)(c)/(d) needs and the model lacked.

Revision ID: d5b19e73c0a8
Revises: c8f3a1d47b06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d5b19e73c0a8"
down_revision = "c8f3a1d47b06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "risks",
        sa.Column("affected_data_subjects", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "risks", sa.Column("existing_safeguards", sa.String(length=2000), nullable=True)
    )
    op.add_column(
        "risks",
        sa.Column("additional_mitigations", sa.String(length=2000), nullable=True),
    )

    op.add_column(
        "dpias",
        sa.Column(
            "section_reviews",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.add_column("dpias", sa.Column("consultation_performed", sa.Boolean(), nullable=True))
    op.add_column("dpias", sa.Column("consulted_party", sa.String(length=300), nullable=True))
    op.add_column("dpias", sa.Column("consulted_role", sa.String(length=150), nullable=True))
    op.add_column(
        "dpias", sa.Column("consulted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "dpias", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("dpias", sa.Column("completed_by", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_dpias_completed_by_users", "dpias", "users", ["completed_by"], ["id"]
    )
    op.add_column(
        "dpias",
        sa.Column("snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("dpias", sa.Column("source_digest", sa.String(length=64), nullable=True))
    op.add_column("dpias", sa.Column("review_reason", sa.String(length=1000), nullable=True))
    op.add_column(
        "dpias", sa.Column("review_flagged_at", sa.DateTime(timezone=True), nullable=True)
    )

    # A screening that concluded "not required" used to be stored as
    # `approved`, which reads on every list as though the assessment was
    # carried out and signed off. It is its own terminal state.
    op.execute(
        """
        UPDATE dpias
           SET status = 'not_required'
         WHERE screening_decision = 'not_required'
           AND status = 'approved'
        """
    )

    op.create_table(
        "dpia_risk_suggestions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "dpia_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("dpias.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("source_key", sa.String(length=200), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="suggested"
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("suggested_safeguards", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_risk_id", sa.Uuid(as_uuid=True), sa.ForeignKey("risks.id"), nullable=True
        ),
        sa.Column(
            "decided_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("dpia_id", "source_key", name="uq_dpia_risk_suggestion_identity"),
    )


def downgrade() -> None:
    op.drop_table("dpia_risk_suggestions")
    op.execute(
        """
        UPDATE dpias
           SET status = 'approved'
         WHERE status = 'not_required'
        """
    )
    for column in (
        "review_flagged_at",
        "review_reason",
        "source_digest",
        "snapshot",
        "consulted_at",
        "consulted_role",
        "consulted_party",
        "consultation_performed",
        "section_reviews",
    ):
        op.drop_column("dpias", column)
    op.drop_constraint("fk_dpias_completed_by_users", "dpias", type_="foreignkey")
    op.drop_column("dpias", "completed_by")
    op.drop_column("dpias", "completed_at")
    for column in (
        "additional_mitigations",
        "existing_safeguards",
        "affected_data_subjects",
    ):
        op.drop_column("risks", column)
