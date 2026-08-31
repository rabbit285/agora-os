"""An audit workspace: scope, snapshot, decisions, verification.

The audit was a title and a blank finding form. Everything an auditor
needed in order to reach a finding — which requirements bind this
organization, which control answers each one, what evidence is on file,
what Veyntra makes of it — already existed elsewhere in the product and
was simply never brought to the audit. So the auditor reconstructed it by
hand, or did not, and the finding form recorded a sentence with nothing
behind it.

This adds:

- **scope and honest timestamps on the audit.** `started_at` alongside
  `completed_at`, and `scope` for what the engagement actually covers.
- **`audit_items`**, one row per scoped requirement, carrying a snapshot
  of the compliance state at preparation and the auditor's decision on
  it. Denormalised on purpose: an audit is a record of what was true
  when somebody looked, and joining live would let today's evidence
  rewrite last quarter's conclusions.
- **context and verification on findings.** Which requirement, which
  control, which evidence was reviewed, and who verified the fix.

It also corrects the state bug it was written alongside. `completed_at`
was set on the way to `completed` and never cleared on the way back, so
an audit could sit at "Planned" while the page beside it printed
"Completed 8/26/2026". Both were reading the database correctly.

Revision ID: e7c2a94b13d8
Revises: d4b81c7f2a95
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e7c2a94b13d8"
down_revision = "d4b81c7f2a95"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- the audit's own state ---------------------------------------
    op.add_column("audits", sa.Column("scope", sa.String(length=2000), nullable=True))
    op.add_column(
        "audits", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "audits", sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "audits",
        sa.Column(
            "prepared_summary",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "audits", sa.Column("framework_name", sa.String(length=200), nullable=True)
    )

    # An audit that got as far as being worked on or finished was started;
    # we do not know when, so the best available honest answer is when it
    # was created. Recorded rather than left null so "In progress with no
    # start date" does not become a second contradictory state.
    op.execute(
        """
        UPDATE audits
        SET started_at = COALESCE(completed_at, created_at)
        WHERE status IN ('in_progress', 'completed') AND started_at IS NULL
        """
    )

    # The reported bug, in the data. A completion stamp on an audit that
    # is not completed is a record of something that did not happen.
    op.execute(
        "UPDATE audits SET completed_at = NULL WHERE status <> 'completed'"
    )

    # --- the workspace ------------------------------------------------
    op.create_table(
        "audit_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "audit_id", sa.Uuid(as_uuid=True), sa.ForeignKey("audits.id"), nullable=False
        ),
        sa.Column(
            "requirement_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("requirements.id"),
            nullable=False,
        ),
        sa.Column("reference_code", sa.String(length=50), nullable=False),
        sa.Column("requirement_title", sa.String(length=300), nullable=False),
        sa.Column("framework_key", sa.String(length=50), nullable=True),
        sa.Column(
            "control_id", sa.Uuid(as_uuid=True), sa.ForeignKey("controls.id"), nullable=True
        ),
        sa.Column("control_title", sa.String(length=300), nullable=True),
        sa.Column(
            "prepared_status",
            sa.String(length=30),
            nullable=False,
            server_default="no_evidence",
        ),
        sa.Column(
            "prepared_confidence", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("prepared_why", sa.String(length=2000), nullable=True),
        sa.Column("prepared_missing", sa.String(length=2000), nullable=True),
        sa.Column(
            "evidence_snapshot",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("applicability", sa.String(length=30), nullable=True),
        sa.Column("applicability_reason", sa.String(length=1000), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=True),
        sa.Column("decision_note", sa.String(length=2000), nullable=True),
        sa.Column(
            "decided_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        # The finding this decision raised. No foreign key: the finding
        # points back at the item too, and declaring both directions makes
        # a cycle the table sorter cannot resolve on a fresh create.
        sa.Column("finding_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Preparing an audit twice reconciles rather than duplicating, and
        # this is what makes that true under a retry rather than merely
        # likely.
        sa.UniqueConstraint(
            "audit_id", "requirement_id", name="uq_audit_item_requirement"
        ),
    )
    op.create_index("ix_audit_items_audit_id", "audit_items", ["audit_id"])
    op.create_index("ix_audit_items_organization_id", "audit_items", ["organization_id"])
    op.create_index("ix_audit_items_decision", "audit_items", ["decision"])
    op.create_index("ix_audit_items_requirement_id", "audit_items", ["requirement_id"])
    op.create_index("ix_audit_items_control_id", "audit_items", ["control_id"])

    # --- findings gain their context ----------------------------------
    op.add_column(
        "audit_findings",
        sa.Column(
            "audit_item_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("audit_items.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_findings",
        sa.Column(
            "requirement_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("requirements.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_findings", sa.Column("requirement_code", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "audit_findings", sa.Column("control_title", sa.String(length=300), nullable=True)
    )
    op.add_column(
        "audit_findings",
        sa.Column(
            "evidence_snapshot",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "audit_findings",
        sa.Column(
            "verified_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.add_column(
        "audit_findings",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audit_findings",
        sa.Column("verification_note", sa.String(length=2000), nullable=True),
    )
    op.create_index("ix_audit_findings_audit_item_id", "audit_findings", ["audit_item_id"])
    op.create_index("ix_audit_findings_requirement_id", "audit_findings", ["requirement_id"])

    op.alter_column(
        "audit_findings",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
    )
    # The old vocabulary had two words. `remediated` meant the work was
    # done, which is not the same as the auditor accepting it — so it
    # becomes "ready for verification" rather than "closed". Reading it
    # as closed would retroactively record verifications nobody performed.
    op.execute(
        "UPDATE audit_findings SET status = 'ready_for_verification' "
        "WHERE status = 'remediated'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE audit_findings SET status = 'remediated' "
        "WHERE status IN ('ready_for_verification', 'remediation_in_progress')"
    )
    op.execute("UPDATE audit_findings SET status = 'open' WHERE status = 'accepted_risk'")
    op.execute("UPDATE audit_findings SET status = 'remediated' WHERE status = 'closed'")
    op.alter_column(
        "audit_findings",
        "status",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
    )
    op.drop_index("ix_audit_findings_requirement_id", table_name="audit_findings")
    op.drop_index("ix_audit_findings_audit_item_id", table_name="audit_findings")
    for column in (
        "verification_note",
        "verified_at",
        "verified_by",
        "evidence_snapshot",
        "control_title",
        "requirement_code",
        "requirement_id",
        "audit_item_id",
    ):
        op.drop_column("audit_findings", column)

    op.drop_index("ix_audit_items_control_id", table_name="audit_items")
    op.drop_index("ix_audit_items_requirement_id", table_name="audit_items")
    op.drop_index("ix_audit_items_decision", table_name="audit_items")
    op.drop_index("ix_audit_items_organization_id", table_name="audit_items")
    op.drop_index("ix_audit_items_audit_id", table_name="audit_items")
    op.drop_table("audit_items")

    for column in (
        "framework_name",
        "prepared_summary",
        "prepared_at",
        "started_at",
        "scope",
    ):
        op.drop_column("audits", column)
