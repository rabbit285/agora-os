"""Core shared platform primitives (docs/DOMAIN_MODEL.md).

Every other domain module (compliance, security, sales, support, automation)
links back to these rather than duplicating them (spec section 80).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
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
    # Sales Lead Finder list export (org policy — see
    # app.routers.sales_lead_finder's export endpoint): an org_admin can
    # turn this off to block CSV export of saved-list contact/company data
    # entirely, independent of the exporting user's own RBAC permission.
    # On by default, matching every other export capability in this build.
    allow_list_export: Mapped[bool] = mapped_column(default=True)


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
    __table_args__ = (
        # A version chain is a line, not a tree. Without these, two
        # people accepting two different uploads against the same
        # previous version both succeed — the endpoint's "has this
        # already been superseded?" check is a read before a write, and
        # loses the race it exists to prevent. The result is two files
        # claiming to supersede one version and no way to say which is
        # current.
        #
        # Partial, because NULL is the normal state: almost every file
        # supersedes nothing and is superseded by nothing.
        #
        # `sqlite_where` as well as `postgresql_where` — SQLite ignores
        # the postgres-only clause and would build a plain unique index
        # instead, making the tests enforce something stricter than
        # production and pass for the wrong reason.
        Index(
            "uq_file_supersedes",
            "supersedes_id",
            unique=True,
            postgresql_where=text("supersedes_id IS NOT NULL"),
            sqlite_where=text("supersedes_id IS NOT NULL"),
        ),
        Index(
            "uq_file_superseded_by",
            "superseded_by_id",
            unique=True,
            postgresql_where=text("superseded_by_id IS NOT NULL"),
            sqlite_where=text("superseded_by_id IS NOT NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # --- who may see this outside the organization --------------------
    #
    # internal (default) | customer_shareable | restricted
    #
    # Default `internal` on purpose, and the whole point of the field. A
    # document nobody has classified is one nobody has decided to share,
    # and the export path treats "not decided" and "not shareable" the
    # same way. The alternative — defaulting to shareable and relying on
    # somebody to mark the sensitive ones — fails silently and outward,
    # which is the one direction a compliance product must not fail in.
    #
    # `restricted` is stronger than internal: a vulnerability report or a
    # penetration test is not merely un-shared, it is one somebody has
    # said must not leave. Export refuses those outright rather than
    # offering an override.
    disclosure: Mapped[str] = mapped_column(
        String(20), nullable=False, default="internal", server_default="internal"
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    # What this document *is*, as opposed to what it was called: SHA-256
    # of the bytes. Two uploads of the same file under different names
    # are one document, and a rename does not create a new one.
    #
    # Nullable, and deliberately so. Uploads are presigned — the client
    # PUTs straight to object storage and the API never sees the bytes at
    # creation time — so the hash is claimed by the client for an early
    # duplicate check and then *verified* against the real content the
    # first time the pipeline reads it. Rows written before this existed
    # have NULL, which the partial unique index tolerates.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    classification: Mapped[str] = mapped_column(String(20), default="internal")
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # --- Document intelligence lifecycle -------------------------------
    # not_analyzed -> uploaded -> parsing -> analyzing -> ready
    #
    # `not_analyzed` is the resting state and the default, because most
    # files in an organization are attachments from other modules that
    # were never submitted for compliance analysis. Without it they would
    # all sit at "uploaded" and render as permanently mid-pipeline, and
    # the UI would poll them forever waiting for a run that was never
    # started.
    #
    # Terminal states are `failed` (we tried and could not) and
    # `unsupported` (we can never read this content type) — kept distinct
    # because the first is worth retrying and the second never is.
    # source | generated_output
    #
    # What kind of thing this file is, recorded rather than guessed from
    # a filename or an extension. A document somebody uploaded is a
    # source of evidence; a report Veyntra produced from the compliance
    # record is a *result* of it, and treating the second as the first
    # is how a product ends up citing its own conclusions back to
    # itself.
    #
    # The distinction has to live in the data because everything
    # downstream keys on it: evidence analysis refuses generated files,
    # the copilot index skips them, and the library lists them apart.
    # Hiding it in the UI would leave every one of those paths open.
    artifact_type: Mapped[str] = mapped_column(
        String(20), default="source", nullable=False, index=True
    )
    # What produced it, for a generated output: "audit_report" or
    # "review_export". Null for anything uploaded.
    origin_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The record it came out of — the audit, the security review. Kept
    # so a report can never be used to evidence the very conclusions it
    # was written from; see app.compliance.artifacts.
    origin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # How that record reads to a person, frozen. "Generated from ISO
    # 42001 Internal Audit" has to keep working after the audit is
    # renamed or archived.
    origin_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(20), default="not_analyzed", index=True)
    # Set when this upload turned out to be bytes the organization
    # already has as a fully analysed document. The row is kept — someone
    # did upload a file and deleting it silently would be a lie about
    # what happened — but it points at the original rather than growing a
    # second set of evidence, gaps and tasks for one real-world policy.
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    # --- version lineage ------------------------------------------------
    #
    # One logical document, many uploads. `supersedes_id` points at the
    # version this one replaces; `superseded_by_id` at the one that
    # replaced it. The head of a chain — the row with no
    # `superseded_by_id` — is the current version, which is the one the
    # library lists, the Copilot answers from, and compliance counts.
    #
    # Two columns rather than one so both directions are a single index
    # lookup: "what is current" is asked on every page, and walking a
    # chain backwards to find the head would make the common question the
    # expensive one.
    #
    # Superseded versions are never deleted. "What did your retention
    # policy say in March" is a question an auditor asks, and a product
    # that overwrote the file cannot answer it.
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    # What this version calls itself, where the document says so, or an
    # internal sequence where it does not. Never invented from the
    # filename — see app.compliance.document_versioning.detect_version_label.
    version_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # A *proposal*, not a link. The document this upload looks like a
    # newer version of, and how sure Veyntra is. Acting on it is a
    # person's decision — `accept_new_version` is what makes it real.
    version_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    # high | medium | low
    version_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Why Veyntra thinks so, in the reader's words. Persisted rather than
    # recomputed: the banner asking somebody to confirm a version link is
    # asking them to agree with an argument, and an argument they cannot
    # read is one they cannot disagree with. Recomputing it per page load
    # would mean re-downloading and re-parsing both documents.
    version_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    # The date the document says it takes effect, exactly as written in
    # it. Text, not a date: "August 2026" is what the policy says, and
    # parsing it into 2026-08-01 would be inventing a day nobody wrote.
    # Absent where the document does not state one.
    version_effective_date: Mapped[str | None] = mapped_column(
        String(60), nullable=True
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Recorded so "ready" can never be claimed over an empty extraction —
    # a document that parsed to nothing is a failure that would otherwise
    # look like success with no matching controls.
    extracted_characters: Mapped[int | None] = mapped_column(nullable=True)
    # Whether this document has been chunked and embedded so the Copilot
    # can retrieve from it. Tracked separately from `processing_status`
    # because they are different pipelines with different failure modes:
    # a document can be read and mapped to controls perfectly while its
    # embedding call fails, and reporting that as "Analyzed" left the
    # customer asking the Copilot about a document it could not see.
    # pending | indexed | failed | unsupported
    index_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # What the model thinks this document *is*, kept separate from
    # `classification` above (which is the security label: internal,
    # confidential…). Nullable because classification is a proposal, and
    # a document we could not read has none.
    document_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    document_domain: Mapped[str | None] = mapped_column(String(80), nullable=True)


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
    # What happened, not how many times we tried to tell someone about
    # it. A retry of the delivery job carries the same key and writes
    # nothing; a genuinely new state transition carries a new one.
    # Nullable for notifications raised before this existed, and for the
    # ad-hoc ones that have no natural key.
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
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
