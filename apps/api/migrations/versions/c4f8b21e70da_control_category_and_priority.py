"""Control category and priority

Both are ordinary attributes of a control that the model simply lacked,
so a compliance team could not record who cares about a control or how
urgent it is without putting it in the description.

`category` is free text on purpose: organizations group controls by their
own taxonomy ("Privacy / Data Governance", "Access Management"), and an
enum of ours would fit nobody and need extending forever.

Revision ID: c4f8b21e70da
Revises: b5d1c82a4f09
Create Date: 2026-08-14 12:05:33.918442
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c4f8b21e70da'
down_revision: str | None = 'b5d1c82a4f09'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column('controls', sa.Column('category', sa.String(length=100), nullable=True))
    op.add_column(
        'controls',
        sa.Column('priority', sa.String(length=10), nullable=False, server_default='medium'),
    )


def downgrade() -> None:
    op.drop_column('controls', 'priority')
    op.drop_column('controls', 'category')
