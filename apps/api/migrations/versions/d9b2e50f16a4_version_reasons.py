"""Why Veyntra thinks an upload is a new version.

The reasons were being computed at detection time and written only to the
audit event, so the banner asking somebody to confirm the link had
nothing to show them. Confirming a version link is agreeing with an
argument; an argument the reader cannot see is one they cannot disagree
with, and a prompt with no reasons is one people learn to click through.

Persisted rather than recomputed, because recomputing means downloading
and re-parsing both documents on every page load.

Revision ID: d9b2e50f16a4
Revises: c8f1a7d34e02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d9b2e50f16a4"
down_revision = "c8f1a7d34e02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column(
            "version_reasons",
            sa.JSON(),
            nullable=False,
            # Existing rows have no recorded reasons. An empty list is
            # honest about that; the banner simply shows the proposal
            # without them, and the next detection fills them in.
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("files", "version_reasons")
