"""One consultation state, and a risk review that can conclude "none"

Two contradictions this removes.

**Consultation had two states for one fact.** `consultation_performed`
recorded the decision, while `consultation_notes` was also one of the
four Article 35(7) sections needing its own sign-off — so the page could
simultaneously show "No consultation performed" and "Nobody has approved
the consultation record", and completion demanded an approval of a
decision that had already been made. Recording the decision is now the
review; `consultation_recorded_by/at` say who made it.

**A DPIA could not conclude that nothing was risky.** Completion
required at least one risk on the register, so a reviewer who read every
candidate and judged none material had to invent one to finish. That is
the opposite of what the record should say. `risk_conclusion`
distinguishes "nobody looked" from "looked, and found none" — only the
second completes, and only with a rationale.

Existing rows are repaired: a DPIA that already has risks against it is
backfilled to `risks_identified`, since that conclusion is exactly what
its register asserts.

Revision ID: e6c2a84f1b39
Revises: d5b19e73c0a8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e6c2a84f1b39"
down_revision = "d5b19e73c0a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dpias", sa.Column("consultation_recorded_by", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_dpias_consultation_recorded_by_users",
        "dpias",
        "users",
        ["consultation_recorded_by"],
        ["id"],
    )
    op.add_column(
        "dpias",
        sa.Column("consultation_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column("dpias", sa.Column("risk_conclusion", sa.String(length=30), nullable=True))
    op.add_column(
        "dpias",
        sa.Column("risk_conclusion_rationale", sa.String(length=2000), nullable=True),
    )
    op.add_column("dpias", sa.Column("risk_reviewed_by", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_dpias_risk_reviewed_by_users", "dpias", "users", ["risk_reviewed_by"], ["id"]
    )
    op.add_column(
        "dpias", sa.Column("risk_reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # A DPIA with risks on its register has already concluded that risks
    # exist. Saying so explicitly means those rows do not suddenly read
    # as "nobody reviewed the risks" under the new rule.
    op.execute(
        """
        UPDATE dpias
           SET risk_conclusion = 'risks_identified'
         WHERE EXISTS (
                   SELECT 1 FROM risks
                    WHERE risks.dpia_id = dpias.id
               )
        """
    )

    # Consultation resolved before this migration was resolved by
    # somebody; the record just never said who. Left null rather than
    # attributed to a guess — an invented actor on an audit record is
    # worse than an absent one.


def downgrade() -> None:
    op.drop_constraint("fk_dpias_risk_reviewed_by_users", "dpias", type_="foreignkey")
    for column in (
        "risk_reviewed_at",
        "risk_reviewed_by",
        "risk_conclusion_rationale",
        "risk_conclusion",
    ):
        op.drop_column("dpias", column)
    op.drop_constraint(
        "fk_dpias_consultation_recorded_by_users", "dpias", type_="foreignkey"
    )
    op.drop_column("dpias", "consultation_recorded_at")
    op.drop_column("dpias", "consultation_recorded_by")
