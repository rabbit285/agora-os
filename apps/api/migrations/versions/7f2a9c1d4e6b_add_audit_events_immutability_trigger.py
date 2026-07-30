"""add audit_events immutability trigger

Revision ID: 7f2a9c1d4e6b
Revises: 3d13a5b8ba86
Create Date: 2026-07-30 19:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "7f2a9c1d4e6b"
down_revision: str | None = "3d13a5b8ba86"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # spec §59 "Audit logs" + app/audit/models.py's append-only contract
    # (docs/DECISIONS.md ADR-0042): a BEFORE UPDATE OR DELETE trigger that
    # unconditionally raises is real DB-level enforcement, and — unlike a
    # plain REVOKE UPDATE/DELETE grant — it cannot be bypassed by the table
    # owner (the same role Alembic itself uses to run migrations), which a
    # role-based REVOKE against an owner-equal application role would not
    # actually stop.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_events is append-only: % is not permitted (row id %)',
                TG_OP, OLD.id;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_immutable
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_immutable ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_event_mutation();")
