"""Evidence suggestions — AI proposals awaiting human approval

Deliberately a separate table from `evidence`, not a flag on it. The
assessment reads `evidence` and ignores this entirely, so a proposal can
never reach a compliance status without someone approving it.

`quote_verified` records whether the passage the model quoted was
actually found in the document. It is the difference between a citation
and an assertion, and it is checked before a suggestion is ever offered
for approval.

Revision ID: d9a3f17c5b82
Revises: c4f8b21e70da
Create Date: 2026-08-16 08:14:22.706551
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'd9a3f17c5b82'
down_revision: str | None = 'c4f8b21e70da'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        'evidence_suggestions',
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('file_id', sa.Uuid(), nullable=False),
        sa.Column('control_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('rationale', sa.String(length=2000), nullable=True),
        sa.Column('quoted_passage', sa.String(length=4000), nullable=True),
        sa.Column('quote_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('evidence_id', sa.Uuid(), nullable=True),
        sa.Column('decided_by', sa.Uuid(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['file_id'], ['files.id']),
        sa.ForeignKeyConstraint(['control_id'], ['controls.id']),
        sa.ForeignKeyConstraint(['evidence_id'], ['evidence.id']),
        sa.ForeignKeyConstraint(['decided_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_evidence_suggestions_organization_id'),
        'evidence_suggestions',
        ['organization_id'],
    )
    op.create_index(
        op.f('ix_evidence_suggestions_file_id'), 'evidence_suggestions', ['file_id']
    )
    op.create_index(
        op.f('ix_evidence_suggestions_control_id'), 'evidence_suggestions', ['control_id']
    )


def downgrade() -> None:
    op.drop_table('evidence_suggestions')
