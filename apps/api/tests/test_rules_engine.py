"""Tests for the Business Rules Engine (spec §90, BIZ-05). Rules are
evaluated from the exact same real event-dispatch point Automation
workflows already use (`app.automation.triggers.dispatch_event`) — these
tests trigger the real underlying action (creating a critical security
alert, registering a high-risk AI system) and assert the rule's real
consequence (a Notification row, an Approval row), not just that a rule
row was saved.
"""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Rules Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _invite_and_accept(
    client: AsyncClient, *, email: str, role_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": email, "role_key": role_key},
        )
    assert created.status_code == 201, created.text
    token = None
    for record in caplog.records:
        match = re.search(r"/invite/([A-Za-z0-9_-]+)", record.message)
        if match:
            token = match.group(1)
    assert token is not None
    await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": token, "full_name": "Invited User", "password": "correct-horse-battery"},
    )


async def test_create_and_list_a_business_rule(client: AsyncClient) -> None:
    await _signup(client, "rules1@example.com", "Rules Org 1")
    created = await client.post(
        "/api/v1/business-rules",
        json={
            "name": "Critical alerts notify CISO",
            "trigger_type": "security_alert",
            "condition_field": "severity",
            "condition_operator": "==",
            "condition_value": "critical",
            "action_type": "notify",
            "action_role_key": "security_manager",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_active"] is True

    listed = await client.get("/api/v1/business-rules")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_unknown_trigger_type_is_rejected(client: AsyncClient) -> None:
    await _signup(client, "rules2@example.com", "Rules Org 2")
    response = await client.post(
        "/api/v1/business-rules",
        json={
            "name": "Bad rule",
            "trigger_type": "not_a_real_trigger",
            "condition_field": "x",
            "condition_operator": "==",
            "condition_value": "y",
            "action_type": "notify",
            "action_role_key": "security_manager",
        },
    )
    assert response.status_code == 422


async def test_critical_security_alert_rule_notifies_every_member_with_the_target_role(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _signup(client, "rules3-admin@example.com", "Rules Org 3")
    await client.post(
        "/api/v1/business-rules",
        json={
            "name": "Critical alerts notify security manager",
            "trigger_type": "security_alert",
            "condition_field": "severity",
            "condition_operator": "==",
            "condition_value": "critical",
            "action_type": "notify",
            "action_role_key": "security_manager",
        },
    )
    await _invite_and_accept(
        client, email="rules3-secmgr@example.com", role_key="security_manager", caplog=caplog
    )

    # Back to the org_admin session to create the triggering alert.
    await client.post("/api/v1/auth/logout")
    await client.post(
        "/api/v1/auth/login",
        json={"email": "rules3-admin@example.com", "password": "correct-horse-battery"},
    )
    created = await client.post(
        "/api/v1/security/alerts", json={"title": "Real critical alert", "severity": "critical"}
    )
    assert created.status_code == 201, created.text

    # Confirm as the security manager that they received a notification.
    await client.post("/api/v1/auth/logout")
    await client.post(
        "/api/v1/auth/login",
        json={"email": "rules3-secmgr@example.com", "password": "correct-horse-battery"},
    )
    notifications = await client.get("/api/v1/notifications")
    assert notifications.status_code == 200
    titles = [n["title"] for n in notifications.json()]
    assert any("Critical alerts notify security manager" in t for t in titles)


async def test_non_matching_severity_does_not_trigger_the_rule(client: AsyncClient) -> None:
    await _signup(client, "rules4@example.com", "Rules Org 4")
    await client.post(
        "/api/v1/business-rules",
        json={
            "name": "Critical only",
            "trigger_type": "security_alert",
            "condition_field": "severity",
            "condition_operator": "==",
            "condition_value": "critical",
            "action_type": "notify",
            "action_role_key": "org_admin",
        },
    )
    await client.post("/api/v1/security/alerts", json={"title": "Low severity", "severity": "low"})

    notifications = await client.get("/api/v1/notifications")
    titles = [n["title"] for n in notifications.json()]
    assert not any("Critical only" in t for t in titles)


async def test_high_risk_ai_system_rule_creates_a_real_approval(client: AsyncClient) -> None:
    await _signup(client, "rules5@example.com", "Rules Org 5")
    await client.post(
        "/api/v1/business-rules",
        json={
            "name": "High-risk AI requires DPO approval",
            "trigger_type": "ai_system_registered",
            "condition_field": "risk_classification",
            "condition_operator": "==",
            "condition_value": "high",
            "action_type": "require_approval",
            "action_role_key": "dpo",
            "action_risk_class": "high",
        },
    )

    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Risky Model", "purpose": "Scoring", "risk_classification": "high"},
    )
    assert created.status_code == 201, created.text

    approvals = await client.get("/api/v1/approvals")
    assert approvals.status_code == 200
    matching = [a for a in approvals.json() if a["action_type"].startswith("business_rule:")]
    assert len(matching) == 1
    assert matching[0]["risk_class"] == "high"
    assert matching[0]["status"] == "pending"


async def test_deactivating_a_rule_stops_it_from_firing(client: AsyncClient) -> None:
    await _signup(client, "rules6@example.com", "Rules Org 6")
    created = await client.post(
        "/api/v1/business-rules",
        json={
            "name": "Toggle rule",
            "trigger_type": "security_alert",
            "condition_field": "severity",
            "condition_operator": "==",
            "condition_value": "critical",
            "action_type": "notify",
            "action_role_key": "org_admin",
        },
    )
    rule_id = created.json()["id"]

    deactivated = await client.patch(f"/api/v1/business-rules/{rule_id}", json={"is_active": False})
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    await client.post("/api/v1/security/alerts", json={"title": "Should not notify", "severity": "critical"})
    notifications = await client.get("/api/v1/notifications")
    titles = [n["title"] for n in notifications.json()]
    assert not any("Toggle rule" in t for t in titles)


async def test_deleting_a_business_rule(client: AsyncClient) -> None:
    await _signup(client, "rules7@example.com", "Rules Org 7")
    created = await client.post(
        "/api/v1/business-rules",
        json={
            "name": "To delete",
            "trigger_type": "new_vendor",
            "condition_field": "name",
            "condition_operator": "!=",
            "condition_value": "impossible-value",
            "action_type": "notify",
            "action_role_key": "org_admin",
        },
    )
    rule_id = created.json()["id"]

    deleted = await client.delete(f"/api/v1/business-rules/{rule_id}")
    assert deleted.status_code == 204

    listed = await client.get("/api/v1/business-rules")
    assert listed.json() == []
