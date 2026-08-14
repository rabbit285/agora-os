"""add framework activations and compliance gaps

Backfills an active FrameworkActivation for every framework an
organization has already built controls against. Without the backfill,
deploying this would make every existing org's frameworks read as
un-adopted overnight and hide work they had already done — the activation
row is new, but their adoption of GDPR is not.

Revision ID: c8d4e1f60a37
Revises: b3f21a7c9d04
Create Date: 2026-08-14 05:44:12.331907
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c8d4e1f60a37'
down_revision: str | None = 'b3f21a7c9d04'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        'framework_activations',
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('framework_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('activated_by', sa.Uuid(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['framework_id'], ['frameworks.id']),
        sa.ForeignKeyConstraint(['activated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'framework_id', name='uq_framework_activation_org_framework'
        ),
    )
    op.create_index(
        op.f('ix_framework_activations_organization_id'),
        'framework_activations',
        ['organization_id'],
    )
    op.create_index(
        op.f('ix_framework_activations_framework_id'), 'framework_activations', ['framework_id']
    )

    op.create_table(
        'compliance_gaps',
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('framework_id', sa.Uuid(), nullable=False),
        sa.Column('requirement_id', sa.Uuid(), nullable=False),
        sa.Column('control_id', sa.Uuid(), nullable=True),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('summary', sa.String(length=2000), nullable=False),
        sa.Column('recommendation', sa.String(length=4000), nullable=True),
        sa.Column('task_id', sa.Uuid(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['framework_id'], ['frameworks.id']),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id']),
        sa.ForeignKeyConstraint(['control_id'], ['controls.id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.PrimaryKeyConstraint('id'),
        # The uniqueness is the reconciliation mechanism, not just an
        # index: it is what makes re-running an assessment update the
        # existing finding instead of stacking duplicates.
        sa.UniqueConstraint(
            'organization_id', 'requirement_id', name='uq_compliance_gap_org_requirement'
        ),
    )
    op.create_index(
        op.f('ix_compliance_gaps_organization_id'), 'compliance_gaps', ['organization_id']
    )
    op.create_index(op.f('ix_compliance_gaps_framework_id'), 'compliance_gaps', ['framework_id'])
    op.create_index(
        op.f('ix_compliance_gaps_requirement_id'), 'compliance_gaps', ['requirement_id']
    )
    op.create_index(op.f('ix_compliance_gaps_control_id'), 'compliance_gaps', ['control_id'])

    # Backfill: any framework an org already has a mapped control against
    # is one it has demonstrably adopted.
    # The DISTINCT has to happen in a subquery: gen_random_uuid() in the
    # select list is distinct on every row by definition, so an org with
    # two controls mapped to the same framework would produce two
    # activation rows and violate the unique constraint.
    op.execute(
        """
        INSERT INTO framework_activations (
            id, organization_id, framework_id, status, activated_at, created_at, updated_at
        )
        SELECT gen_random_uuid(), pairs.organization_id, pairs.framework_id,
               'active', now(), now(), now()
        FROM (
            SELECT DISTINCT c.organization_id, r.framework_id
            FROM controls c
            JOIN control_mappings cm ON cm.control_id = c.id
            JOIN requirements r ON r.id = cm.requirement_id
        ) AS pairs
        ON CONFLICT ON CONSTRAINT uq_framework_activation_org_framework DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table('compliance_gaps')
    op.drop_table('framework_activations')
