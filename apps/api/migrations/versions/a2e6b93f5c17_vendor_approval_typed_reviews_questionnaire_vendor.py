"""Vendor approval decision, typed vendor reviews, vendor questionnaires

`approval_state` adds the outcome real vendor reviews usually reach.
Without "conditionally approved" a reviewer holding one outstanding
question has to either block a vendor the business needs or approve them
outright and lose the caveat — which is how a review process quietly
becomes a rubber stamp.

Existing vendors get 'not_submitted': they have not been through this
decision, and inventing an approval for them would be exactly the
fabricated record this workflow is meant to prevent.

Revision ID: a2e6b93f5c17
Revises: f3c8a71d0b64
Create Date: 2026-08-14 08:44:19.773204
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'a2e6b93f5c17'
down_revision: str | None = 'f3c8a71d0b64'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column(
        'vendors',
        sa.Column(
            'approval_state', sa.String(length=30), nullable=False, server_default='not_submitted'
        ),
    )
    op.add_column('vendors', sa.Column('approval_conditions', sa.String(length=2000), nullable=True))
    op.add_column(
        'vendors', sa.Column('approval_decided_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column('vendors', sa.Column('approval_decided_by', sa.Uuid(), nullable=True))
    op.add_column('vendors', sa.Column('compliance_owner_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_vendors_approval_decided_by', 'vendors', 'users', ['approval_decided_by'], ['id']
    )
    op.create_foreign_key(
        'fk_vendors_compliance_owner', 'vendors', 'users', ['compliance_owner_id'], ['id']
    )

    op.add_column(
        'vendor_assessments',
        sa.Column(
            'assessment_type', sa.String(length=20), nullable=False, server_default='general'
        ),
    )
    op.add_column('vendor_assessments', sa.Column('findings', sa.JSON(), nullable=True))

    op.add_column('questionnaires', sa.Column('vendor_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_questionnaires_vendor', 'questionnaires', 'vendors', ['vendor_id'], ['id']
    )
    op.create_index(op.f('ix_questionnaires_vendor_id'), 'questionnaires', ['vendor_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_questionnaires_vendor_id'), table_name='questionnaires')
    op.drop_constraint('fk_questionnaires_vendor', 'questionnaires', type_='foreignkey')
    op.drop_column('questionnaires', 'vendor_id')

    op.drop_column('vendor_assessments', 'findings')
    op.drop_column('vendor_assessments', 'assessment_type')

    op.drop_constraint('fk_vendors_compliance_owner', 'vendors', type_='foreignkey')
    op.drop_constraint('fk_vendors_approval_decided_by', 'vendors', type_='foreignkey')
    for column in (
        'compliance_owner_id',
        'approval_decided_by',
        'approval_decided_at',
        'approval_conditions',
        'approval_state',
    ):
        op.drop_column('vendors', column)
