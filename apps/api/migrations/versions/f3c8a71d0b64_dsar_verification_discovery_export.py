"""DSAR identity verification, discovery findings, and export record

The verification columns are the point. An access request asks a
controller to hand over everything it holds about a named person, so
answering one without establishing who is asking is how one person's data
reaches another. Existing rows default to 'pending', which is the correct
and conservative reading: nobody verified them, because there was nothing
to verify them with.

Revision ID: f3c8a71d0b64
Revises: e7b2f04c1a95
Create Date: 2026-08-14 07:58:31.472905
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'f3c8a71d0b64'
down_revision: str | None = 'e7b2f04c1a95'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column(
        'dsars',
        sa.Column(
            'verification_status', sa.String(length=20), nullable=False, server_default='pending'
        ),
    )
    op.add_column('dsars', sa.Column('verification_method', sa.String(length=200), nullable=True))
    op.add_column('dsars', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('dsars', sa.Column('verified_by', sa.Uuid(), nullable=True))
    op.add_column('dsars', sa.Column('discovery_findings', sa.JSON(), nullable=True))
    op.add_column('dsars', sa.Column('discovery_run_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('dsars', sa.Column('export_file_id', sa.Uuid(), nullable=True))
    op.add_column(
        'dsars', sa.Column('export_generated_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key('fk_dsars_verified_by', 'dsars', 'users', ['verified_by'], ['id'])
    op.create_foreign_key('fk_dsars_export_file', 'dsars', 'files', ['export_file_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_dsars_export_file', 'dsars', type_='foreignkey')
    op.drop_constraint('fk_dsars_verified_by', 'dsars', type_='foreignkey')
    for column in (
        'export_generated_at',
        'export_file_id',
        'discovery_run_at',
        'discovery_findings',
        'verified_by',
        'verified_at',
        'verification_method',
        'verification_status',
    ):
        op.drop_column('dsars', column)
