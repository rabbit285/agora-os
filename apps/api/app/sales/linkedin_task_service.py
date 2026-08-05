"""Manual LinkedIn outreach (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md
§12 and the task brief's explicit LinkedIn prohibitions). This module
does exactly three things and nothing else: stores an approved profile
URL a human pasted in, lets the frontend open it in a new tab, and turns
a human-drafted message into a real `core.Task` for a human to send
manually. No scraping, no automated login, no automated connection
requests or messaging, no official API integration (none is configured
in this build) — the task itself, not this service, is the record of
outreach intent.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import Task
from app.sales.models import Contact

_LINKEDIN_URL_PREFIXES = ("https://www.linkedin.com/", "https://linkedin.com/")


def is_plausible_linkedin_url(url: str) -> bool:
    """A real sanity check, not fabricated verification — this build never
    confirms the profile exists or matches the contact, only that the URL
    at least points at linkedin.com before it's stored and shown as a
    clickable link."""
    return url.startswith(_LINKEDIN_URL_PREFIXES)


async def create_linkedin_outreach_task(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    contact: Contact,
    linkedin_url: str | None,
    message: str,
    ip_address: str | None,
    user_agent: str | None,
) -> Task:
    if linkedin_url is not None:
        contact.linkedin_url = linkedin_url

    task = Task(
        organization_id=organization_id,
        title=f"LinkedIn outreach: {contact.full_name}",
        description=message,
        module="sales",
        priority="normal",
        assignee_id=actor_user_id,
        created_by=actor_user_id,
        entity_type="sales_contact",
        entity_id=str(contact.id),
    )
    db.add(task)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="sales.lead_finder.linkedin_task.created",
        object_type="task",
        object_id=str(task.id),
        after_state={"contact_id": str(contact.id), "linkedin_url": contact.linkedin_url},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return task
