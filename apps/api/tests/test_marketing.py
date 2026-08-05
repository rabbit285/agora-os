from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketing.models import DemoRequest


async def test_submit_demo_request_is_public_and_persists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No signup, no session cookie — a genuinely anonymous visitor."""
    response = await client.post(
        "/api/v1/marketing/demo-requests",
        json={
            "full_name": "Jordan Rivera",
            "work_email": "Jordan.Rivera@Example.com",
            "company_name": "Rivera Consulting",
            "company_size": "11-50",
            "country": "Germany",
            "primary_interest": "compliance",
            "message": "Evaluating for our DPIA workflow.",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert "id" in body and "created_at" in body

    row = await db_session.get(DemoRequest, uuid.UUID(body["id"]))
    assert row is not None
    # Email is normalized to lowercase, matching every other email-intake
    # path in this codebase (app.identity.service).
    assert row.work_email == "jordan.rivera@example.com"
    assert row.company_name == "Rivera Consulting"
    assert row.status == "new"


async def test_submit_demo_request_rejects_invalid_company_size(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/marketing/demo-requests",
        json={
            "full_name": "Jordan Rivera",
            "work_email": "jordan@example.com",
            "company_name": "Rivera Consulting",
            "company_size": "not-a-real-bracket",
            "country": "Germany",
            "primary_interest": "compliance",
        },
    )
    assert response.status_code == 422


async def test_submit_demo_request_message_is_optional(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/marketing/demo-requests",
        json={
            "full_name": "Jordan Rivera",
            "work_email": "jordan2@example.com",
            "company_name": "Rivera Consulting",
            "company_size": "1-10",
            "country": "Germany",
            "primary_interest": "other",
        },
    )
    assert response.status_code == 201, response.text


async def test_submit_demo_request_records_audit_event_with_no_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.post(
        "/api/v1/marketing/demo-requests",
        json={
            "full_name": "Jordan Rivera",
            "work_email": "jordan3@example.com",
            "company_name": "Rivera Consulting",
            "company_size": "51-200",
            "country": "Germany",
            "primary_interest": "security",
        },
    )
    assert response.status_code == 201, response.text
    demo_request_id = response.json()["id"]

    from app.audit.models import AuditEvent

    event = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "marketing.demo_request.created",
                AuditEvent.object_id == demo_request_id,
            )
        )
    ).scalar_one()
    assert event.organization_id is None
    assert event.actor_user_id is None
    assert event.after_state["company_name"] == "Rivera Consulting"
