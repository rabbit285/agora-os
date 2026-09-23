"""DSAR sources: searchability separated from relevance

The old `connected` boolean answered "can Veyntra query this?" and was
then reused, wrongly, as a reason to rank a source relevant. Those are
different questions — one is about our plumbing, the other about whether
this person's data is plausibly there — and collapsing them made
"Veyntra can search this cheaply" an argument for searching it.

So `connected` becomes `search_capability`, which names the five real
states, and relevance is computed from the requester and the register
alone.

`potential_sources` carries the systems a processing activity actually
reaches. A RoPA entry is compliance context, not a database: knowing an
activity is in scope tells you where to look next, not that the person's
records are in the activity itself.

Revision ID: c4f9a1e63d78
Revises: b3e8f2a71c94
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4f9a1e63d78"
down_revision = "b3e8f2a71c94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dsar_scope_sources",
        sa.Column(
            "search_capability",
            sa.String(30),
            nullable=False,
            server_default="manual_follow_up",
        ),
    )
    op.add_column(
        "dsar_scope_sources", sa.Column("potential_sources", sa.JSON(), nullable=True)
    )
    # Why a reviewer left an important source out. Required at exclusion
    # time so a narrowed scope carries its own justification.
    op.add_column(
        "dsar_scope_sources", sa.Column("exclusion_reason", sa.String(1000), nullable=True)
    )

    # Carry the old boolean across rather than dropping the distinction:
    # a source that was connected really was searchable.
    op.execute(
        "UPDATE dsar_scope_sources SET search_capability = "
        "CASE WHEN connected THEN 'searchable' ELSE 'manual_follow_up' END"
    )
    op.drop_column("dsar_scope_sources", "connected")

    # Legacy Sales/Support scope rows and their findings, from when
    # discovery searched product modules this product no longer has. Left
    # in place they would keep appearing in scope lists and response
    # packages as though they were current data sources.
    op.execute(
        "DELETE FROM dsar_discovered_items WHERE source_key IN "
        "('internal:support', 'internal:sales')"
    )
    op.execute(
        "DELETE FROM dsar_scope_sources WHERE source_key IN "
        "('internal:support', 'internal:sales')"
    )

    # "medium" was never shown to anybody as a word; the screen says
    # "Possible relevance". Renamed so the stored value and the label
    # agree.
    op.execute("UPDATE dsar_scope_sources SET relevance = 'possible' WHERE relevance = 'medium'")


def downgrade() -> None:
    op.add_column(
        "dsar_scope_sources",
        sa.Column("connected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE dsar_scope_sources SET connected = (search_capability = 'searchable')"
    )
    op.drop_column("dsar_scope_sources", "exclusion_reason")
    op.drop_column("dsar_scope_sources", "potential_sources")
    op.drop_column("dsar_scope_sources", "search_capability")
    op.execute("UPDATE dsar_scope_sources SET relevance = 'medium' WHERE relevance = 'possible'")
