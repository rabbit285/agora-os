"""DPIA sections, screening outcome, and residual risk level

Article 35(7) enumerates what a DPIA must contain. The model held one
free-text `findings` column, so a reviewer could not tell whether
necessity had been assessed and left unwritten or never considered at
all. Each section is now separately assessable.

Revision ID: e7b2f04c1a95
Revises: d1a5c93b7e28
Create Date: 2026-08-14 07:12:58.664201
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'e7b2f04c1a95'
down_revision: str | None = 'd1a5c93b7e28'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column('dpias', sa.Column('processing_description', sa.String(length=4000), nullable=True))
    op.add_column('dpias', sa.Column('necessity_assessment', sa.String(length=4000), nullable=True))
    op.add_column(
        'dpias', sa.Column('proportionality_assessment', sa.String(length=4000), nullable=True)
    )
    op.add_column('dpias', sa.Column('consultation_notes', sa.String(length=4000), nullable=True))
    op.add_column('dpias', sa.Column('residual_risk_level', sa.String(length=20), nullable=True))
    op.add_column('dpias', sa.Column('screening_outcome', sa.String(length=20), nullable=True))
    op.add_column('dpias', sa.Column('screening_findings', sa.JSON(), nullable=True))


def downgrade() -> None:
    for column in (
        'screening_findings',
        'screening_outcome',
        'residual_risk_level',
        'consultation_notes',
        'proportionality_assessment',
        'necessity_assessment',
        'processing_description',
    ):
        op.drop_column('dpias', column)
