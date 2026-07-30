"""Regression tests for the audit-event `object_id` bug found during the
product completeness audit (2026-07-30): several routers called
`record_event(object_id=str(obj.id))` immediately after `db.add(obj)`, before
any `await db.flush()`. Since `UUIDPrimaryKeyMixin.id` uses a Python-side
`default=uuid.uuid4` (`app/db/base.py`), SQLAlchemy only assigns it at flush
time — so `obj.id` was still `None` and `str(None)` (the literal four-character
string `"None"`) was written to `audit_events.object_id`.

Each test below drives the real HTTP endpoint (not the service function
directly) so it exercises the exact code path that was broken, then reads the
`audit_events` row back from the database and asserts `object_id` is a
well-formed UUID matching the created resource's real id.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.audit.service import record_event


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Audit Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _latest_event_for_action(db_session: AsyncSession, *, action: str) -> AuditEvent:
    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.created_at.desc())
    )
    event = result.scalars().first()
    assert event is not None, f"No audit_events row was written for action={action!r}"
    return event


def _assert_real_object_id(event: AuditEvent, expected_id: str) -> None:
    assert event.object_id != "None", (
        f"audit_events.object_id was the literal string 'None' for action="
        f"{event.action!r} — the object was not flushed before its id was captured."
    )
    assert event.object_id == expected_id
    # Confirm it's genuinely a parseable UUID, not just "not the word None".
    uuid.UUID(event.object_id)


async def test_record_event_rejects_literal_none_object_id(db_session: AsyncSession) -> None:
    """Direct unit test of the permanent guard added to `record_event` itself
    — this is the defense-in-depth fix that makes the whole bug class fail
    loudly instead of silently corrupting the audit trail, regardless of
    whether every call site has been individually audited."""
    with pytest.raises(ValueError, match="literal string 'None'"):
        await record_event(
            db_session,
            organization_id=uuid.uuid4(),
            actor_user_id=None,
            action="test.guard_check",
            object_type="test_object",
            object_id=str(None),
        )


async def test_sales_account_created_audit_event_has_real_object_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "audit-sales-account@example.com", "Audit Sales Account Org")
    response = await client.post("/api/v1/sales/accounts", json={"name": "Audit Evidence Co"})
    assert response.status_code == 201
    account_id = response.json()["id"]

    event = await _latest_event_for_action(db_session, action="sales.account.created")
    _assert_real_object_id(event, account_id)


async def test_sales_opportunity_created_audit_event_has_real_object_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "audit-sales-opp@example.com", "Audit Sales Opp Org")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Opp Parent Co"})
    account_id = account.json()["id"]

    response = await client.post(
        "/api/v1/sales/opportunities", json={"account_id": account_id, "title": "Audit deal"}
    )
    assert response.status_code == 201
    opportunity_id = response.json()["id"]

    event = await _latest_event_for_action(db_session, action="sales.opportunity.created")
    _assert_real_object_id(event, opportunity_id)


async def test_security_asset_created_audit_event_has_real_object_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "audit-security-asset@example.com", "Audit Security Asset Org")
    response = await client.post(
        "/api/v1/security/assets", json={"name": "Audit Server", "asset_type": "server"}
    )
    assert response.status_code == 201
    asset_id = response.json()["id"]

    event = await _latest_event_for_action(db_session, action="security.asset.created")
    _assert_real_object_id(event, asset_id)


async def test_security_finding_created_audit_event_has_real_object_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "audit-security-finding@example.com", "Audit Security Finding Org")
    response = await client.post(
        "/api/v1/security/findings",
        json={"title": "Audit finding", "category": "vulnerability", "severity": "medium"},
    )
    assert response.status_code == 201
    finding_id = response.json()["id"]

    event = await _latest_event_for_action(db_session, action="security.finding.created")
    _assert_real_object_id(event, finding_id)


async def test_support_customer_created_audit_event_has_real_object_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "audit-support-customer@example.com", "Audit Support Customer Org")
    response = await client.post(
        "/api/v1/support/customers",
        json={"name": "Audit Customer Inc", "email": "billing@audit-customer.example"},
    )
    assert response.status_code == 201
    customer_id = response.json()["id"]

    event = await _latest_event_for_action(db_session, action="support.customer.created")
    _assert_real_object_id(event, customer_id)


async def test_compliance_risk_created_audit_event_has_real_object_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "audit-compliance-risk@example.com", "Audit Compliance Risk Org")
    response = await client.post(
        "/api/v1/compliance/risks",
        json={"title": "Audit risk", "likelihood": "medium", "impact": "medium"},
    )
    assert response.status_code == 201
    risk_id = response.json()["id"]

    event = await _latest_event_for_action(db_session, action="compliance.risk.created")
    _assert_real_object_id(event, risk_id)


async def test_compliance_policy_created_audit_event_has_real_object_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "audit-compliance-policy@example.com", "Audit Compliance Policy Org")
    response = await client.post("/api/v1/compliance/policies", json={"title": "Audit policy"})
    assert response.status_code == 201
    policy_id = response.json()["id"]

    event = await _latest_event_for_action(db_session, action="compliance.policy.created")
    _assert_real_object_id(event, policy_id)


async def test_compliance_evidence_created_audit_event_has_real_object_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "audit-compliance-evidence@example.com", "Audit Compliance Evidence Org")

    upload = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "evidence.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
        },
    )
    assert upload.status_code == 200
    file_id = upload.json()["file_id"]

    response = await client.post(
        "/api/v1/compliance/evidence", json={"file_id": file_id, "title": "Audit evidence"}
    )
    assert response.status_code == 201
    evidence_id = response.json()["id"]

    event = await _latest_event_for_action(db_session, action="compliance.evidence.created")
    _assert_real_object_id(event, evidence_id)


async def test_no_audit_event_ever_has_literal_none_object_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Broad sweep: after exercising every "created" action across every
    module in one run, assert that not a single audit_events row anywhere in
    the database has the literal string "None" as its object_id."""
    await _signup(client, "audit-sweep@example.com", "Audit Sweep Org")

    account = await client.post("/api/v1/sales/accounts", json={"name": "Sweep Co"})
    account_id = account.json()["id"]
    await client.post(
        "/api/v1/sales/opportunities", json={"account_id": account_id, "title": "Sweep deal"}
    )
    await client.post(
        "/api/v1/security/assets", json={"name": "Sweep Asset", "asset_type": "server"}
    )
    await client.post(
        "/api/v1/security/findings",
        json={"title": "Sweep finding", "category": "vulnerability", "severity": "low"},
    )
    await client.post(
        "/api/v1/support/customers",
        json={"name": "Sweep Customer", "email": "billing@sweep-customer.example"},
    )
    await client.post(
        "/api/v1/compliance/risks",
        json={"title": "Sweep risk", "likelihood": "low", "impact": "low"},
    )
    await client.post("/api/v1/compliance/policies", json={"title": "Sweep policy"})
    upload = await client.post(
        "/api/v1/files/upload-url",
        json={"filename": "sweep.pdf", "content_type": "application/pdf", "size_bytes": 512},
    )
    await client.post(
        "/api/v1/compliance/evidence",
        json={"file_id": upload.json()["file_id"], "title": "Sweep evidence"},
    )

    result = await db_session.execute(select(AuditEvent.action, AuditEvent.object_id))
    rows = result.all()
    assert rows, "expected at least one audit_events row after exercising the sweep"
    offenders = [action for action, object_id in rows if object_id == "None"]
    assert not offenders, f"audit_events rows with object_id=='None' for actions: {offenders}"
