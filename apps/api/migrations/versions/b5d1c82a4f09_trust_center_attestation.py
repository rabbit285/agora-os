"""Trust Center attestation for certification claims

`independently_assessed` and `certified` assert what an external party
concluded, not what we built. They are the only statements on a trust
page a buyer cannot verify from the rest of it, which makes them the ones
worth faking — so they now require an attestation document and a named
person.

Existing rows keep their status untouched. Backfilling an attestation
nobody supplied would manufacture exactly the record this is meant to
prevent; an existing `certified` row simply carries no attestation until
someone attaches one.

Revision ID: b5d1c82a4f09
Revises: a2e6b93f5c17
Create Date: 2026-08-14 09:22:07.551938
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'b5d1c82a4f09'
down_revision: str | None = 'a2e6b93f5c17'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column(
        'trust_center_items', sa.Column('attestation_file_id', sa.Uuid(), nullable=True)
    )
    op.add_column(
        'trust_center_items', sa.Column('attestation_note', sa.String(length=1000), nullable=True)
    )
    op.add_column('trust_center_items', sa.Column('attested_by', sa.Uuid(), nullable=True))
    op.add_column(
        'trust_center_items', sa.Column('attested_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_trust_center_items_attestation_file',
        'trust_center_items',
        'files',
        ['attestation_file_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_trust_center_items_attested_by', 'trust_center_items', 'users', ['attested_by'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_trust_center_items_attested_by', 'trust_center_items', type_='foreignkey'
    )
    op.drop_constraint(
        'fk_trust_center_items_attestation_file', 'trust_center_items', type_='foreignkey'
    )
    for column in ('attested_at', 'attested_by', 'attestation_note', 'attestation_file_id'):
        op.drop_column('trust_center_items', column)
