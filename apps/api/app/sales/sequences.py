"""Sequences and Campaigns (spec §23) — a multi-step outreach cadence
engine. `advance_due_enrollments` is the one place a step actually fires:
it builds a real `OutreachMessage` from the step's template and sends it
through `app.sales.service.send_outreach_message`, so every automated
send is gated by the exact same Compliance check (spec §91) a manually
composed message is — there is no parallel, ungated send path.

Template substitution is deliberately simple (`{{first_name}}` from
`Contact.full_name`'s first token) rather than a full templating engine —
this is a v1 cadence engine, not a marketing-automation platform.

Step advancement is a plain synchronous function, callable from a real
endpoint (`POST /sales/sequences/process-due-steps`) rather than
Temporal-scheduled — Automation's own Temporal migration (a separate,
larger piece of work) is the natural place to wire a recurring schedule
onto this function later; the function itself is already real and
independently testable without that wiring existing yet.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sales.models import Contact, OutreachMessage, Sequence, SequenceEnrollment, SequenceStep
from app.sales.service import send_outreach_message


def _render_template(template: str, contact: Contact) -> str:
    first_name = contact.full_name.split(" ")[0] if contact.full_name else ""
    return template.replace("{{first_name}}", first_name).replace(
        "{{full_name}}", contact.full_name
    )


async def enroll_contacts(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    sequence: Sequence,
    contact_ids: list[uuid.UUID],
    campaign_id: uuid.UUID | None = None,
) -> list[SequenceEnrollment]:
    enrollments: list[SequenceEnrollment] = []
    for contact_id in contact_ids:
        enrollment = SequenceEnrollment(
            organization_id=organization_id,
            sequence_id=sequence.id,
            contact_id=contact_id,
            campaign_id=campaign_id,
            next_step_due_at=datetime.now(UTC),
        )
        db.add(enrollment)
        enrollments.append(enrollment)
    await db.flush()
    return enrollments


async def advance_due_enrollments(
    db: AsyncSession, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> int:
    """Fires the current due step for every active enrollment whose
    `next_step_due_at` has passed, then advances it to the next step (or
    marks it `completed` if there is none). Returns the number of
    enrollments processed."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(SequenceEnrollment).where(
            SequenceEnrollment.organization_id == organization_id,
            SequenceEnrollment.status == "active",
            SequenceEnrollment.next_step_due_at <= now,
        )
    )
    enrollments = list(result.scalars().all())
    processed = 0

    for enrollment in enrollments:
        steps_result = await db.execute(
            select(SequenceStep)
            .where(SequenceStep.sequence_id == enrollment.sequence_id)
            .order_by(SequenceStep.order_index.asc())
        )
        steps = list(steps_result.scalars().all())
        if enrollment.current_step_index >= len(steps):
            enrollment.status = "completed"
            continue

        step = steps[enrollment.current_step_index]
        contact = await db.get(Contact, enrollment.contact_id)
        if contact is None:
            enrollment.status = "exited"
            continue

        message = OutreachMessage(
            organization_id=organization_id,
            contact_id=contact.id,
            channel=step.channel,
            subject=_render_template(step.subject_template, contact)
            if step.subject_template
            else None,
            body=_render_template(step.body_template, contact),
        )
        db.add(message)
        await db.flush()
        await send_outreach_message(
            db,
            organization_id=organization_id,
            message=message,
            contact=contact,
            actor_user_id=actor_user_id,
        )

        enrollment.current_step_index += 1
        processed += 1
        if enrollment.current_step_index >= len(steps):
            enrollment.status = "completed"
        else:
            next_step = steps[enrollment.current_step_index]
            enrollment.next_step_due_at = now + timedelta(days=next_step.wait_days)

    return processed
