"""A DPIA's screening decision, and a risk level that is not assumed

Two things a DPIA page could not say honestly.

**The screening was never stored.** `record_dpia_screening` wrote an
audit event and returned its result; nothing reached the DPIA. So a
screen could not show what was recommended, which criteria triggered it,
who decided, or what they decided — the auditable half of the exercise
existed only in the event log, and the DPIA detail page had nothing to
render.

**The inherent risk defaulted to "low".** A DPIA with no risks raised
against it reported `Inherent risk: Low`, which is not a cautious
default — it is an assessment nobody performed, stated as fact, on the
document whose entire purpose is to record that somebody assessed the
risk. The column becomes nullable, and null means "not assessed"
everywhere it is read.

Existing rows keep whatever level they were given, because a DPIA
somebody set to `high` said something. Only the ones still sitting on
the default with no risks behind them are cleared.

Revision ID: c8f3a1d47b06
Revises: b7d24e0f9c15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8f3a1d47b06"
down_revision = "b7d24e0f9c15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- the human decision, kept beside the recommendation -------------
    op.add_column(
        "dpias",
        sa.Column("screening_decision", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "dpias",
        sa.Column(
            "screening_decided_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "dpias",
        sa.Column("screening_decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dpias", sa.Column("screening_rationale", sa.String(length=2000), nullable=True)
    )
    op.add_column(
        "dpias", sa.Column("screened_at", sa.DateTime(timezone=True), nullable=True)
    )

    # --- a risk level that can say "nobody has assessed this" -----------
    op.alter_column("dpias", "risk_level", existing_type=sa.String(length=20), nullable=True)
    op.alter_column("dpias", "risk_level", server_default=None)

    # Only the ones that never had a risk raised against them, and are
    # still sitting on the default. A level somebody chose is a statement
    # and stays.
    op.execute(
        sa.text(
            """
            UPDATE dpias
               SET risk_level = NULL
             WHERE risk_level = 'low'
               AND NOT EXISTS (
                   SELECT 1 FROM risks WHERE risks.dpia_id = dpias.id
               )
            """
        )
    )

    # A DPIA that has not been screened is not a draft assessment yet.
    op.execute(
        sa.text(
            """
            UPDATE dpias
               SET status = 'screening'
             WHERE status = 'draft'
               AND screening_outcome IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE dpias SET status = 'draft' WHERE status = 'screening'"))
    op.execute(sa.text("UPDATE dpias SET risk_level = 'low' WHERE risk_level IS NULL"))
    op.alter_column(
        "dpias",
        "risk_level",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="low",
    )
    op.drop_column("dpias", "screened_at")
    op.drop_column("dpias", "screening_rationale")
    op.drop_column("dpias", "screening_decided_at")
    op.drop_column("dpias", "screening_decided_by")
    op.drop_column("dpias", "screening_decision")
