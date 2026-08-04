"""Business Rules Engine (spec §90). A `BusinessRule` is real structured
data — a single field/operator/value condition against a real event's
payload, plus a real action — never text embedded in an AI prompt
(spec's own "Business rules should be separate from prompts").
Evaluation piggybacks on the exact same event-dispatch point Automation
workflows already use (`app.automation.triggers.dispatch_event`), so
every existing real event source (new vendor, security alert, AI system
registered, ...) automatically evaluates configured rules too, without
a second parallel event-hook system.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CONDITION_OPERATORS = frozenset({"==", "!=", ">", ">=", "<", "<="})
ACTION_TYPES = frozenset({"require_approval", "notify"})


class BusinessRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # One of app.automation.triggers.dispatch_event's real trigger_type
    # values (e.g. "security_alert", "new_vendor", "ai_system_registered")
    # — the exact same vocabulary Automation workflows already trigger on.
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Condition: payload[condition_field] <condition_operator> condition_value.
    condition_field: Mapped[str] = mapped_column(String(50), nullable=False)
    condition_operator: Mapped[str] = mapped_column(String(5), nullable=False)
    condition_value: Mapped[str] = mapped_column(String(200), nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # For "notify": the role whose members get notified. For
    # "require_approval": the role conceptually responsible for deciding
    # it (real approval-role enforcement remains RBAC's job, not
    # duplicated here — this is descriptive metadata on the Approval).
    action_role_key: Mapped[str] = mapped_column(String(50), nullable=False)
    action_risk_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
