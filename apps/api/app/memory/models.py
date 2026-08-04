"""Business AI Memory (spec §89). A `MemoryEntry` is structured, typed
data (`entry_type`) with real provenance (`provenance_type`/
`provenance_id` name the exact source row, when one exists) — never a
raw conversation transcript treated as ground truth, per spec's own
"Do not rely only on raw conversation history. Create structured
memory." Deletion is a soft `status` flip, not a row removal, so
provenance survives an administrator's correction/deletion action for
audit purposes (see app.routers.memory for the RBAC-gated correct/
delete endpoints spec §89 requires).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# spec §89's 7 named categories to store.
ENTRY_TYPES = frozenset(
    {
        "approved_fact",
        "approved_answer",
        "policy",
        "business_rule",
        "preference",
        "past_decision",
        "workflow_outcome",
    }
)

# "manual" is an administrator directly recording an entry (the primary
# path — spec's "Create organization memory carefully" cautions against
# indiscriminate automatic capture); "policy" is the one real automatic
# hook, fired when a Policy is published (app.routers.compliance.
# update_policy_status), since publishing is itself already a careful,
# deliberate admin action worth recording without further curation.
PROVENANCE_TYPES = frozenset({"manual", "policy"})


class MemoryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memory_entries"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    provenance_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # No FK constraint — provenance_id points at a different table
    # depending on provenance_type (e.g. a Policy id), so it is an
    # informational reference, not a relational join target.
    provenance_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|deleted
