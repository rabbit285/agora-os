"""Compliance domain services.

`record_assessment` is the one cross-module hook this slice ships (spec
section 80: do not build disconnected modules) — a failed control
assessment creates a shared `core.Task` automatically, the same primitive
Tasks/Approvals already use, rather than the Compliance module inventing
its own follow-up mechanism.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import Control, ControlAssessment
from app.core.models import Task


async def record_assessment(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    control: Control,
    status: str,
    notes: str | None,
    assessed_by: uuid.UUID | None,
) -> ControlAssessment:
    assessment = ControlAssessment(
        organization_id=organization_id,
        control_id=control.id,
        status=status,
        notes=notes,
        assessed_by=assessed_by,
    )
    db.add(assessment)
    await db.flush()

    control.status = "needs_review" if status in ("fail", "partial") else "implemented"

    if status == "fail":
        db.add(
            Task(
                organization_id=organization_id,
                title=f"Remediate failed control: {control.title}",
                description=notes,
                module="compliance",
                priority="high",
                status="open",
            )
        )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=assessed_by,
        action="compliance.control.assessed",
        object_type="control",
        object_id=str(control.id),
        after_state={"status": status},
    )
    return assessment
