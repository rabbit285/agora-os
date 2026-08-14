"""AI governance profile, assessment types, and residual risk

Adds the inventory detail the EU AI Act expects (who uses it, who is
affected, what data it touches, who is accountable), splits AIAssessment
into typed assessments so the regulatory screening and the privacy review
stop being the same undifferentiated row, and gives Risk a residual
rating plus links to the AI system or DPIA it was raised against.

Existing ai_assessments rows are backfilled to 'general', which is what
they were: neither an EU AI Act screening nor a privacy assessment, since
neither concept existed when they were written.

Revision ID: d1a5c93b7e28
Revises: c8d4e1f60a37
Create Date: 2026-08-14 06:31:44.208517
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'd1a5c93b7e28'
down_revision: str | None = 'c8d4e1f60a37'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column('ai_systems', sa.Column('description', sa.String(length=2000), nullable=True))
    op.add_column('ai_systems', sa.Column('model_name', sa.String(length=200), nullable=True))
    op.add_column(
        'ai_systems',
        sa.Column('internal_users', sa.JSON(), nullable=False, server_default='[]'),
    )
    op.add_column(
        'ai_systems',
        sa.Column('affected_users', sa.JSON(), nullable=False, server_default='[]'),
    )
    op.add_column(
        'ai_systems',
        sa.Column('processed_data', sa.JSON(), nullable=False, server_default='[]'),
    )
    op.add_column('ai_systems', sa.Column('business_owner_id', sa.Uuid(), nullable=True))
    op.add_column('ai_systems', sa.Column('technical_owner_id', sa.Uuid(), nullable=True))
    op.add_column('ai_systems', sa.Column('governance_owner_id', sa.Uuid(), nullable=True))
    op.add_column(
        'ai_systems', sa.Column('last_reviewed_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_ai_systems_business_owner', 'ai_systems', 'users', ['business_owner_id'], ['id']
    )
    op.create_foreign_key(
        'fk_ai_systems_technical_owner', 'ai_systems', 'users', ['technical_owner_id'], ['id']
    )
    op.create_foreign_key(
        'fk_ai_systems_governance_owner', 'ai_systems', 'users', ['governance_owner_id'], ['id']
    )

    op.add_column(
        'ai_assessments',
        sa.Column('assessment_type', sa.String(length=20), nullable=False, server_default='general'),
    )
    op.add_column('ai_assessments', sa.Column('findings', sa.JSON(), nullable=True))

    op.add_column('risks', sa.Column('ai_system_id', sa.Uuid(), nullable=True))
    op.add_column('risks', sa.Column('dpia_id', sa.Uuid(), nullable=True))
    op.add_column('risks', sa.Column('residual_likelihood', sa.String(length=10), nullable=True))
    op.add_column('risks', sa.Column('residual_impact', sa.String(length=10), nullable=True))
    op.create_foreign_key('fk_risks_ai_system', 'risks', 'ai_systems', ['ai_system_id'], ['id'])
    op.create_foreign_key('fk_risks_dpia', 'risks', 'dpias', ['dpia_id'], ['id'])
    op.create_index(op.f('ix_risks_ai_system_id'), 'risks', ['ai_system_id'])
    op.create_index(op.f('ix_risks_dpia_id'), 'risks', ['dpia_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_risks_dpia_id'), table_name='risks')
    op.drop_index(op.f('ix_risks_ai_system_id'), table_name='risks')
    op.drop_constraint('fk_risks_dpia', 'risks', type_='foreignkey')
    op.drop_constraint('fk_risks_ai_system', 'risks', type_='foreignkey')
    for column in ('residual_impact', 'residual_likelihood', 'dpia_id', 'ai_system_id'):
        op.drop_column('risks', column)

    op.drop_column('ai_assessments', 'findings')
    op.drop_column('ai_assessments', 'assessment_type')

    for constraint in (
        'fk_ai_systems_governance_owner',
        'fk_ai_systems_technical_owner',
        'fk_ai_systems_business_owner',
    ):
        op.drop_constraint(constraint, 'ai_systems', type_='foreignkey')
    for column in (
        'last_reviewed_at',
        'governance_owner_id',
        'technical_owner_id',
        'business_owner_id',
        'processed_data',
        'affected_users',
        'internal_users',
        'model_name',
        'description',
    ):
        op.drop_column('ai_systems', column)
