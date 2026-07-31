"""Tests for spec §66 multi-channel notification dispatch:
`app.core.notifications.notify` (in-app always fires; email/webhook are
real, opt-in per user via NotificationPreference; Slack/Teams honestly
never deliver in this build) and its API surface
(GET/PUT /notifications/preferences, PATCH /organizations/current for the
org-level webhook URL).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications import notify
from app.identity.models import User


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Notify Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_notify_always_creates_the_in_app_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "notify1@example.com", "Notify Org 1")
    user = (await db_session.execute(select(User))).scalars().first()
    assert user is not None

    notification = await notify(
        db_session, organization_id=org_id, user_id=user.id, title="Hello"
    )
    await db_session.commit()
    assert notification.channels_requested == ["in_app"]
    assert notification.channels_delivered == ["in_app"]


async def test_notify_delivers_email_only_when_the_user_opted_in(
    client: AsyncClient, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    org_id = await _signup(client, "notify2@example.com", "Notify Org 2")

    # Not opted in yet — email requested but not delivered.
    me = await client.get("/api/v1/auth/me")
    user_id = uuid.UUID(me.json()["id"])

    notification = await notify(
        db_session,
        organization_id=org_id,
        user_id=user_id,
        title="Urgent",
        channels=["email"],
    )
    await db_session.commit()
    assert notification.channels_requested == ["in_app", "email"]
    assert notification.channels_delivered == ["in_app"]

    # Opt in via the real endpoint, then the next notify() call delivers.
    opt_in = await client.put(
        "/api/v1/notifications/preferences", json={"channel": "email", "enabled": True}
    )
    assert opt_in.status_code == 200

    with caplog.at_level("INFO", logger="agora.notifications"):
        notification2 = await notify(
            db_session,
            organization_id=org_id,
            user_id=user_id,
            title="Urgent again",
            channels=["email"],
        )
        await db_session.commit()
    assert notification2.channels_delivered == ["in_app", "email"]
    assert any("Notification email to" in record.message for record in caplog.records)


async def test_notify_never_marks_slack_or_teams_as_delivered(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "notify3@example.com", "Notify Org 3")
    me = await client.get("/api/v1/auth/me")
    user_id = uuid.UUID(me.json()["id"])

    for channel in ("slack", "teams"):
        await client.put(
            "/api/v1/notifications/preferences", json={"channel": channel, "enabled": True}
        )

    notification = await notify(
        db_session,
        organization_id=org_id,
        user_id=user_id,
        title="Test",
        channels=["slack", "teams"],
    )
    await db_session.commit()
    assert notification.channels_requested == ["in_app", "slack", "teams"]
    assert notification.channels_delivered == ["in_app"]


async def test_notify_delivers_webhook_when_configured_and_opted_in(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.core.notifications as notifications_module

    org_id = await _signup(client, "notify4@example.com", "Notify Org 4")
    me = await client.get("/api/v1/auth/me")
    user_id = uuid.UUID(me.json()["id"])

    configured = await client.patch(
        "/api/v1/organizations/current",
        json={"name": "Notify Org 4", "notification_webhook_url": "https://hooks.example.test/x"},
    )
    assert configured.status_code == 200
    assert configured.json()["notification_webhook_url"] == "https://hooks.example.test/x"

    await client.put(
        "/api/v1/notifications/preferences", json={"channel": "webhook", "enabled": True}
    )

    calls: list[str] = []

    async def _fake_dispatch(*, url: str, title: str, body: str | None, link: str | None) -> bool:
        calls.append(url)
        return True

    monkeypatch.setattr(notifications_module, "_dispatch_notification_webhook", _fake_dispatch)

    notification = await notify(
        db_session,
        organization_id=org_id,
        user_id=user_id,
        title="Webhook test",
        channels=["webhook"],
    )
    await db_session.commit()
    assert calls == ["https://hooks.example.test/x"]
    assert notification.channels_delivered == ["in_app", "webhook"]


async def test_notification_preferences_are_scoped_to_the_current_user(
    client: AsyncClient,
) -> None:
    await _signup(client, "notify5@example.com", "Notify Org 5")
    await client.put(
        "/api/v1/notifications/preferences", json={"channel": "email", "enabled": True}
    )
    listed = await client.get("/api/v1/notifications/preferences")
    assert listed.status_code == 200
    channels = {p["channel"]: p["enabled"] for p in listed.json()}
    assert channels["email"] is True
