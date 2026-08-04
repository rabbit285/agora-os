"""Reporting (spec §65). A generated `Report` row is a real artifact: its
`storage_key` points at real rendered bytes in object storage (MinIO
locally, S3 in AWS), produced by `app.reporting.rendering` from real,
live-queried organizational data (`app.reporting.content`) — never a
placeholder file or a fabricated "generated" status with nothing behind
it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # One of app.reporting.schemas.REPORT_TYPES' 14 spec-named keys.
    report_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # One of app.reporting.schemas.REPORT_FORMATS: pdf|docx|xlsx|csv. Spec
    # §65's 5th export option, "Secure link", isn't a distinct file format
    # — every report here is already delivered exclusively via a signed,
    # time-limited download URL (GET /reports/{id}/download, the same
    # presign_download primitive app.routers.files uses), never inlined
    # or emailed, so that mechanism realizes "Secure link" for all 4
    # formats rather than being a 5th thing to generate.
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    # generating | completed | failed — generation is synchronous today
    # (aggregate queries + render, no AI call, typically sub-second), so a
    # row is written already-`completed` or `failed`; the state exists so
    # the API and frontend polling contract don't have to change if a
    # slower report type someday needs a background job.
    status: Mapped[str] = mapped_column(String(20), default="completed")
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
