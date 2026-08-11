"""add apollo customer oauth connection fields

Additive and nullable-only (plus one defaulted integer), so an existing
deployment upgrades without touching any stored row's meaning. Existing
organizations therefore start with no Apollo connection at all — which is
exactly the intended post-migration state: nobody inherits the old
deployment-wide APOLLO_API_KEY (see
docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md and
docs/APOLLO_OAUTH_MIGRATION_AUDIT.md).

Revision ID: a1c7e93f5b20
Revises: 6a77f8c48d95
Create Date: 2026-08-07 04:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1c7e93f5b20'
down_revision: str | None = '6a77f8c48d95'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column(
        'integration_connections',
        sa.Column('provider_user_email', sa.String(length=320), nullable=True),
    )
    op.add_column(
        'integration_connections',
        sa.Column('provider_workspace_id', sa.String(length=200), nullable=True),
    )
    op.add_column(
        'integration_connections',
        sa.Column('provider_workspace_name', sa.String(length=200), nullable=True),
    )
    op.add_column(
        'integration_connections', sa.Column('token_type', sa.String(length=40), nullable=True)
    )
    op.add_column(
        'integration_connections',
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'integration_connections',
        sa.Column('refreshed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'integration_connections',
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'integration_connections', sa.Column('last_error_code', sa.String(length=60), nullable=True)
    )
    op.add_column(
        'integration_connections',
        sa.Column('reauthorization_required_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'integration_connections',
        sa.Column('disconnected_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'integration_connections',
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'integration_connections',
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
    )

    # One *active* Apollo connection per organization (architecture §2).
    # Partial index rather than a plain unique constraint so historical,
    # disconnected rows are retained for provenance and audit rather than
    # deleted — and so a later multi-connection model is an index change,
    # not a destructive redesign.
    op.create_index(
        'ix_integration_connections_one_active_apollo',
        'integration_connections',
        ['organization_id', 'connector_key'],
        unique=True,
        postgresql_where=sa.text("connector_key = 'apollo' AND disconnected_at IS NULL"),
        sqlite_where=sa.text("connector_key = 'apollo' AND disconnected_at IS NULL"),
    )

    # Attributes Apollo credit spend to the specific connection (and
    # therefore the specific connected Apollo user) that incurred it, not
    # just the Agora organization.
    op.add_column(
        'sales_provider_credit_usage',
        sa.Column('connection_id', sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_sales_provider_credit_usage_connection_id',
        'sales_provider_credit_usage',
        'integration_connections',
        ['connection_id'],
        ['id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_sales_provider_credit_usage_connection_id',
        'sales_provider_credit_usage',
        type_='foreignkey',
    )
    op.drop_column('sales_provider_credit_usage', 'connection_id')
    op.drop_index(
        'ix_integration_connections_one_active_apollo', table_name='integration_connections'
    )
    op.drop_column('integration_connections', 'version')
    op.drop_column('integration_connections', 'revoked_at')
    op.drop_column('integration_connections', 'disconnected_at')
    op.drop_column('integration_connections', 'reauthorization_required_at')
    op.drop_column('integration_connections', 'last_error_code')
    op.drop_column('integration_connections', 'last_success_at')
    op.drop_column('integration_connections', 'refreshed_at')
    op.drop_column('integration_connections', 'connected_at')
    op.drop_column('integration_connections', 'token_type')
    op.drop_column('integration_connections', 'provider_workspace_name')
    op.drop_column('integration_connections', 'provider_workspace_id')
    op.drop_column('integration_connections', 'provider_user_email')
