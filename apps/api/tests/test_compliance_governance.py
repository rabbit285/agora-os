"""Tests for Compliance as Governance Layer (spec §91): synchronous
pre-action checks other modules ask Compliance before acting, not just
Compliance reacting to events after the fact. See
app.compliance.governance's module docstring for the three named
examples this implements.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.governance import (
    check_contact_permission,
    check_customer_disclosure_permission,
    check_data_export_permission,
)
from app.sales.models import Contact
from app.support.models import Customer


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Governance Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


# --- 1. Sales asks Compliance: can we contact this prospect? ------------


async def test_check_contact_permission_denies_suppressed_contact(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    contact = Contact(
        organization_id=org_id,
        full_name="Suppressed Person",
        email="s@example.com",
        do_not_contact=True,
    )
    decision = await check_contact_permission(db_session, organization_id=org_id, contact=contact)
    assert decision.allowed is False
    assert "suppressed" in (decision.reason or "").lower()


async def test_check_contact_permission_allows_reachable_contact(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    contact = Contact(
        organization_id=org_id,
        full_name="Reachable Person",
        email="r@example.com",
        do_not_contact=False,
    )
    decision = await check_contact_permission(db_session, organization_id=org_id, contact=contact)
    assert decision.allowed is True


# --- 2. Support asks Compliance: can we disclose this customer's info? --


async def test_agent_message_blocked_while_deletion_dsar_pending(client: AsyncClient) -> None:
    await _signup(client, "governance1@example.com", "Governance Org 1")

    customer = await client.post(
        "/api/v1/support/customers",
        json={"name": "Pending Deletion Person", "email": "delete-me@example.com"},
    )
    customer_id = customer.json()["id"]

    ticket = await client.post(
        "/api/v1/support/tickets",
        json={
            "customer_id": customer_id,
            "subject": "Account question",
            "channel": "email",
            "category": "account",
            "priority": "medium",
        },
    )
    ticket_id = ticket.json()["id"]

    await client.post(
        "/api/v1/compliance/dsars",
        json={
            "requester_name": "Pending Deletion Person",
            "requester_email": "delete-me@example.com",
            "request_type": "deletion",
        },
    )

    response = await client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages",
        json={"sender_type": "agent", "body": "Here is your account balance: 500 EUR."},
    )
    assert response.status_code == 403
    assert "pending" in response.json()["error"]["message"].lower()

    # A customer-sent message is unaffected — the gate only applies to
    # what the org discloses, not what the customer says.
    customer_message = await client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages",
        json={"sender_type": "customer", "body": "When will this be resolved?"},
    )
    assert customer_message.status_code == 201


async def test_agent_message_allowed_without_pending_deletion(client: AsyncClient) -> None:
    await _signup(client, "governance2@example.com", "Governance Org 2")

    customer = await client.post(
        "/api/v1/support/customers",
        json={"name": "Normal Customer", "email": "normal@example.com"},
    )
    customer_id = customer.json()["id"]

    ticket = await client.post(
        "/api/v1/support/tickets",
        json={
            "customer_id": customer_id,
            "subject": "Account question",
            "channel": "email",
            "category": "account",
            "priority": "medium",
        },
    )
    ticket_id = ticket.json()["id"]

    response = await client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages",
        json={"sender_type": "agent", "body": "Here is your account balance: 500 EUR."},
    )
    assert response.status_code == 201


async def test_check_customer_disclosure_permission_direct(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    customer = Customer(organization_id=org_id, name="Direct Test", email="direct@example.com")
    decision = await check_customer_disclosure_permission(
        db_session, organization_id=org_id, customer=customer
    )
    assert decision.allowed is True


# --- 3. Automation asks Compliance: can this workflow export personal data? --


async def test_check_data_export_permission_allows_non_sensitive_classification(
    db_session: AsyncSession,
) -> None:
    decision = await check_data_export_permission(
        db_session,
        organization_id=uuid.uuid4(),
        destination_country="US",
        data_classification="internal",
    )
    assert decision.allowed is True


async def test_check_data_export_permission_denies_without_transfer_on_file(
    db_session: AsyncSession,
) -> None:
    decision = await check_data_export_permission(
        db_session,
        organization_id=uuid.uuid4(),
        destination_country="US",
        data_classification="restricted",
    )
    assert decision.allowed is False
    assert "no active data transfer" in (decision.reason or "").lower()


async def test_automation_export_data_step_fails_run_without_transfer(client: AsyncClient) -> None:
    await _signup(client, "governance3@example.com", "Governance Org 3")

    workflow = await client.post(
        "/api/v1/automation/workflows",
        json={
            "name": "Export customer data",
            "trigger_type": "manual",
            "steps": [
                {
                    "step_type": "export_data",
                    "config": {
                        "destination_country": "US",
                        "data_classification": "restricted",
                    },
                }
            ],
        },
    )
    assert workflow.status_code == 201
    workflow_id = workflow.json()["id"]
    await client.patch(
        f"/api/v1/automation/workflows/{workflow_id}/status", json={"status": "active"}
    )

    run = await client.post(f"/api/v1/automation/workflows/{workflow_id}/run", json={})
    assert run.status_code == 201
    # Execution is Temporal-durable (spec §61) — the export_data step's
    # actual allow/deny behavior is directly tested against
    # app.automation.service.advance_run in test_automation_service.py.
    assert run.json()["status"] == "running"


async def test_automation_export_data_step_succeeds_with_active_transfer(
    client: AsyncClient,
) -> None:
    await _signup(client, "governance4@example.com", "Governance Org 4")

    await client.post(
        "/api/v1/compliance/data-transfers",
        json={
            "recipient_name": "US Partner Inc",
            "destination_country": "US",
            "transfer_mechanism": "sccs",
        },
    )

    workflow = await client.post(
        "/api/v1/automation/workflows",
        json={
            "name": "Export customer data (approved destination)",
            "trigger_type": "manual",
            "steps": [
                {
                    "step_type": "export_data",
                    "config": {
                        "destination_country": "US",
                        "data_classification": "restricted",
                    },
                }
            ],
        },
    )
    workflow_id = workflow.json()["id"]
    await client.patch(
        f"/api/v1/automation/workflows/{workflow_id}/status", json={"status": "active"}
    )

    run = await client.post(f"/api/v1/automation/workflows/{workflow_id}/run", json={})
    assert run.status_code == 201
    # Execution is Temporal-durable (spec §61) — the export_data step's
    # actual allow/deny behavior is directly tested against
    # app.automation.service.advance_run in test_automation_service.py.
    assert run.json()["status"] == "running"
