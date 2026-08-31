"""The named conditions behind a gap

Revision ID: d41e7a06c8b2
Revises: c3f9e28d4b71
Create Date: 2026-08-20

A gap used to be raised whenever a requirement had evidence but no
recorded human pass — which is an assessment that has not happened, not a
deficiency. Gaps now require a condition that is demonstrably unmet, and
this column holds which ones, as the coverage analysis named them at the
moment the finding was raised.

Stored rather than re-derived: somebody working a finding must not have
its wording change underneath them because an unrelated document landed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d41e7a06c8b2"
down_revision = "c3f9e28d4b71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "compliance_gaps",
        sa.Column(
            "missing_conditions",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("compliance_gaps", "missing_conditions")
