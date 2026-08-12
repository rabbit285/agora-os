"""add subscriptions and billing webhook events

Backfills a Subscription row for every existing organization so the
entitlement service does not lock anyone out on deploy. Existing orgs are
marked `active`, not `trialing`: they predate billing, and starting a
14-day countdown against accounts that were never told about one would
lock live customers out two weeks after this migration ran.

Revision ID: b3f21a7c9d04
Revises: a1c7e93f5b20
Create Date: 2026-08-12 10:12:44.918233
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'b3f21a7c9d04'
down_revision: str | None = 'a1c7e93f5b20'
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        'subscriptions',
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('plan_key', sa.String(length=20), nullable=False),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('tax_id', sa.String(length=64), nullable=True),
        sa.Column('tax_id_country', sa.String(length=2), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id'),
        sa.UniqueConstraint('stripe_subscription_id'),
    )
    op.create_index(
        op.f('ix_subscriptions_organization_id'), 'subscriptions', ['organization_id']
    )
    op.create_index(
        op.f('ix_subscriptions_stripe_customer_id'), 'subscriptions', ['stripe_customer_id']
    )

    op.create_table(
        'billing_webhook_events',
        sa.Column('stripe_event_id', sa.String(length=255), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        # The unique constraint is the idempotency mechanism itself, not
        # just an index: it is what makes a replayed Stripe event a no-op
        # even if two deliveries land concurrently.
        sa.UniqueConstraint('stripe_event_id'),
    )

    # Backfill. `plan_key` mirrors whatever the org already had, so nobody
    # is silently upgraded or downgraded by this migration.
    op.execute(
        """
        INSERT INTO subscriptions (
            id, organization_id, status, plan_key, cancel_at_period_end,
            created_at, updated_at
        )
        SELECT gen_random_uuid(), o.id, 'active', o.plan_key, false, now(), now()
        FROM organizations o
        """
    )


def downgrade() -> None:
    op.drop_table('billing_webhook_events')
    op.drop_index(op.f('ix_subscriptions_stripe_customer_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_organization_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
