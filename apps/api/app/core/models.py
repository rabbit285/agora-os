"""Core shared platform primitives (docs/DOMAIN_MODEL.md).

Every other domain module (compliance, security, sales, support, automation)
links back to these rather than duplicating them (spec section 80).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    # spec §66 Webhook notification channel — a real outbound POST target,
    # org-scoped rather than per-user (a webhook receiver is an
    # organization's integration, not an individual's preference).
    notification_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # spec §64 Billing — "Plans architecture" (the header itself carries
    # spec's own "architecture" qualifier): every org is on a real plan,
    # entitlements are really enforced (app.billing.service), but there is
    # no real payment collection — an org_admin picks their own plan
    # directly (see app.routers.billing), disclosed in
    # docs/KNOWN_LIMITATIONS.md rather than faking a Stripe checkout.
    plan_key: Mapped[str] = mapped_column(String(20), default="starter")
    # spec §B5 "Customer Data Control" — export; deletion. Requesting
    # deletion is a real, visible, cancellable, audited precursor state;
    # the actual irreversible purge only runs via a separately-confirmed
    # execute call (see app.core.organization_deletion).
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Sales Lead Finder outreach eligibility (spec — see
    # docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §12): when set, a provider
    # record/contact missing lawful-basis metadata is "Requires Review"
    # rather than "Eligible" for campaign/sequence enrollment. Off by
    # default — this build has no structured per-contact consent model, so
    # this single org-level toggle is a documented, honest simplification
    # rather than a fabricated jurisdiction/consent engine.
    requires_lawful_basis_metadata: Mapped[bool] = mapped_column(default=False)


class LegalEntity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """spec §53 multi-tenancy "Support:" tier (Organization/Legal Entity/
    Business Unit/Team) — distinct from that same section's "Future:" tier
    (parent organization / subsidiaries / agency-consultant multi-client
    mode), which remains genuinely unbuilt, disclosed in
    KNOWN_LIMITATIONS.md. Every organization gets exactly one `is_default`
    entity at signup (see `app.identity.service`); archival uses
    `is_active`, never a destructive delete (spec §73)."""

    __tablename__ = "legal_entities"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_legal_entity_org_name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_team_org_name"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("legal_entities.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_role_org_key"),)

    # null organization_id => system-seeded role, available to every org
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_system: Mapped[bool] = mapped_column(default=False)


class Permission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("roles.id"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("permissions.id"), primary_key=True
    )


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class MembershipRole(Base):
    __tablename__ = "membership_roles"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memberships.id"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("roles.id"), primary_key=True
    )


class Invitation(UUIDPrimaryKeyMixin, Base):
    """An org.users.manage holder's invite of an email address to a specific
    system role. Accepting creates (or attaches an existing) User plus an
    active Membership with `invited_by` set — see `app.core.invitations`."""

    __tablename__ = "invitations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role_key: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    module: Mapped[str] = mapped_column(String(50), default="core")
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Nullable: rows created before this field existed have no recorded
    # creator. Every task created going forward always sets it.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Generic link back to the record this task concerns (spec §44's
    # "Entity" field) — a string pair like AuditEvent.object_type/object_id
    # rather than 8+ nullable FK columns, one per possible origin module.
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # [{"text": str, "done": bool}, ...] — spec §44's "Checklist" field.
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class TaskComment(UUIDPrimaryKeyMixin, Base):
    """spec §44's "Comments" field."""

    __tablename__ = "task_comments"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskEvidence(UUIDPrimaryKeyMixin, Base):
    """spec §44's "Evidence" field — attaches an already-uploaded `File`
    (the same upload primitive Compliance's own Evidence model attaches)
    rather than a second file-upload pipeline."""

    __tablename__ = "task_evidence"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(150), nullable=False)
    risk_class: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Nullable: rows created before this field existed have no recorded
    # module. Every approval created going forward always sets it (spec
    # §45's Approval Center "Module" column).
    module: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # spec §45's "AI-generated?" column — real and available, but every
    # current call site is a deterministic rule/policy/workflow trigger, not
    # an AI model authoring free-text content awaiting sign-off, so it is
    # honestly always False today (see docs/DECISIONS.md).
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class File(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "files"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    classification: Mapped[str] = mapped_column(String(20), default="internal")
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(UUIDPrimaryKeyMixin, Base):
    """spec §66's In-app channel is always fired unconditionally; the other
    three named channels (Email, Slack, Teams — Webhook is org-level, see
    `Organization.notification_webhook_url`) are opt-in per user via
    `NotificationPreference` and honestly report what was actually
    delivered, never a fabricated "sent" (spec §82) — see
    `app.core.notifications.notify`."""

    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    # Kept for backward compatibility with any direct reader; always
    # "in_app" — see channels_requested/channels_delivered for the real
    # multi-channel picture.
    channel: Mapped[str] = mapped_column(String(20), default="in_app")
    channels_requested: Mapped[list[str]] = mapped_column(JSON, default=list)
    channels_delivered: Mapped[list[str]] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationPreference(UUIDPrimaryKeyMixin, Base):
    """Per-user, per-channel opt-in (spec §66 "User preferences"). No row
    for a channel means disabled — `in_app` never needs a row since it
    always fires. Only `email`/`webhook` can ever actually deliver in this
    build even when enabled (see `app.core.notifications`); `slack`/`teams`
    preferences can still be stored (a user's stated intent) but never
    result in a real delivery here."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "channel", name="uq_notification_pref_user_channel"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True)
