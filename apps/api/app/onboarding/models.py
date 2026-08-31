"""Onboarding Experience (spec §68) — a real 10-step guided setup wizard
that runs once per organization after signup. `OnboardingProfile` is one
row per organization, updated in place as the user moves through steps;
`current_step` lets the frontend resume where a user left off rather than
restarting. Steps 8 ("Connect tools") and 9 ("Upload knowledge") have no
dedicated fields here — they link to the real, already-existing
Integrations and Knowledge upload flows rather than duplicating them
(spec §80). Step 10's "Business AI Readiness" output is computed live
from real organization data at read time (`app.onboarding.service.
compute_readiness`), never stored — it changes as the organization's real
data changes, the same "no stale rollup" principle
`GET /security/overview` already follows.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OnboardingProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "onboarding_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, unique=True
    )
    # Step 1/2: Company / Business profile.
    industry: Mapped[str | None] = mapped_column(String(150), nullable=True)
    employee_count_range: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Step 3: Choose goals — spec's 5 named checkboxes, stored by key
    # ("improve_compliance", "improve_security", "find_more_customers",
    # "automate_customer_support", "automate_business_operations").
    selected_goals: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Step 4: Compliance profile — which seeded Frameworks matter to them.
    selected_framework_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Company facts that determine which frameworks are in scope. Kept
    # here rather than inferred, because framework applicability is a
    # legal question and every recommendation has to be traceable to
    # something the organization actually declared — see
    # app.compliance.framework_applicability.
    #
    # All default False: an unanswered question must never manufacture an
    # obligation.
    operates_in_eu: Mapped[bool] = mapped_column(default=False, nullable=False)
    sells_to_eu_customers: Mapped[bool] = mapped_column(default=False, nullable=False)
    processes_personal_data: Mapped[bool] = mapped_column(default=False, nullable=False)
    processes_special_category_data: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    uses_third_party_ai: Mapped[bool] = mapped_column(default=False, nullable=False)
    builds_ai_features: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_data_processor: Mapped[bool] = mapped_column(default=False, nullable=False)
    sells_to_enterprise: Mapped[bool] = mapped_column(default=False, nullable=False)
    sector: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Step 5: Security profile.
    primary_cloud_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Step 6: Sales profile.
    sales_focus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Step 7: Support profile.
    support_channels: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 1-10, matching the spec's step numbering; 10 means the readiness
    # step has been reached (not necessarily "completed_at" set yet).
    current_step: Mapped[int] = mapped_column(default=1)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
