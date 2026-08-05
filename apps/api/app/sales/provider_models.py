"""Sales Lead Finder data-provider models (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md). Separate module from
`app.sales.models` (the pre-existing Account/Contact/Lead/Opportunity
domain) so the provider-neutral discovery/enrichment layer — provenance,
credit usage, saved searches, lists, suppression, import/enrichment jobs —
reads as its own bounded addition rather than growing the original module
past its original scope.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SalesProviderRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provenance for a single provider-returned company or person record —
    written only when the user acts on a search result (save/enrich/list),
    never for every row a search response returns (see architecture doc
    §7/§8: search results themselves are cached, not persisted)."""

    __tablename__ = "sales_provider_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    # company | person
    record_type: Mapped[str] = mapped_column(String(10), nullable=False)
    provider_record_id: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_domain: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    normalized_email: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # verified | provider_supplied | unverified | unavailable | stale | user_entered | demo
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    # none | partial | complete | failed
    enrichment_status: Mapped[str] = mapped_column(String(10), default="none")
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    linked_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_accounts.id"), nullable=True, index=True
    )
    linked_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_contacts.id"), nullable=True, index=True
    )
    imported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    imported_by_workflow_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    credit_usage_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_provider_credit_usage.id"), nullable=True
    )


class SalesProviderCreditUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_provider_credit_usage"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    # search_companies | search_people | enrich_company | enrich_person | find_decision_makers
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    estimated_credits: Mapped[int] = mapped_column(nullable=False)
    # Unknown until the provider's own response reports a real number.
    actual_credits: Mapped[int | None] = mapped_column(nullable=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    requested_by_workflow_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    succeeded: Mapped[bool] = mapped_column(default=True)


class SalesSavedSearch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_saved_searches"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # company | person
    search_type: Mapped[str] = mapped_column(String(10), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(30), default="apollo")
    columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    sort: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    density: Mapped[str] = mapped_column(String(20), default="comfortable")
    is_shared: Mapped[bool] = mapped_column(default=False)
    last_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result_count: Mapped[int | None] = mapped_column(nullable=True)


class SalesList(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_lists"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # company | person
    list_type: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_shared: Mapped[bool] = mapped_column(default=False)


class SalesListItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_list_items"

    list_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_lists.id"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_accounts.id"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_contacts.id"), nullable=True
    )
    added_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # The same Account/Contact added to a List twice is never legitimate
    # (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §10). Partial indexes
    # (only enforced when the respective column is populated) since a row
    # has exactly one of account_id/contact_id set, never both.
    __table_args__ = (
        Index(
            "ix_sales_list_items_list_account_unique",
            "list_id",
            "account_id",
            unique=True,
            postgresql_where=text("account_id IS NOT NULL"),
            sqlite_where=text("account_id IS NOT NULL"),
        ),
        Index(
            "ix_sales_list_items_list_contact_unique",
            "list_id",
            "contact_id",
            unique=True,
            postgresql_where=text("contact_id IS NOT NULL"),
            sqlite_where=text("contact_id IS NOT NULL"),
        ),
    )


class SalesSuppressionEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Independent of `Contact.do_not_contact` so a person can be suppressed
    before they're ever saved as a Contact (architecture doc §12)."""

    __tablename__ = "sales_suppression_entries"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    email: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_contacts.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class SalesImportJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_import_jobs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # company | person
    record_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # pending | running | succeeded | failed | partial
    status: Mapped[str] = mapped_column(String(10), default="pending")
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    column_mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    total_rows: Mapped[int] = mapped_column(default=0)
    imported_rows: Mapped[int] = mapped_column(default=0)
    skipped_rows: Mapped[int] = mapped_column(default=0)
    error_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SalesEnrichmentJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_enrichment_jobs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    # enrich_company | enrich_person | find_decision_makers
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    # pending | running | succeeded | failed | partial
    status: Mapped[str] = mapped_column(String(10), default="pending")
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    target_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    estimated_credits: Mapped[int] = mapped_column(default=0)
    actual_credits: Mapped[int | None] = mapped_column(nullable=True)
    succeeded_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)
    error_records: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
