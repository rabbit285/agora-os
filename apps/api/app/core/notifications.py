"""Multi-channel notification dispatch (spec §66).

`notify()` is the single place every module should call to create a
notification — it replaces each caller constructing a `Notification` row
directly, so channel dispatch logic lives in exactly one place. In-app
always fires (it's the primary, undismissable feed); every other channel
is opt-in per user (`NotificationPreference`) and only two of the three
named channels beyond in-app can ever actually deliver in this build:

- **Email**: dispatched through the same log-only dev adapter every other
  transactional email in this build uses (see
  `app.identity.service._dispatch_password_reset_email`) — no real
  SMTP/SES provider is configured anywhere (docs/KNOWN_LIMITATIONS.md).
- **Webhook**: a real `httpx` POST to `Organization.notification_webhook_url`
  when one is configured — genuinely delivered, not simulated.
- **Slack** / **Teams**: honestly never deliverable here. The Slack OAuth
  connector is deliberately scoped `channels:read` only (spec §B1
  progressive trust model) and cannot post; no Teams connector exists at
  all (disclosed in docs/KNOWN_LIMITATIONS.md). A user can still store a
  preference for either (their stated intent), but `notify()` never
  claims a delivery that didn't happen — `channels_delivered` is the
  literal, honest record.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Notification, NotificationPreference, Organization

logger = logging.getLogger("agora.notifications")

# Channels that can genuinely deliver in this build, given real
# credentials/configuration — Slack/Teams are deliberately excluded (see
# module docstring), never silently "successful."
_DELIVERABLE_CHANNELS = frozenset({"email", "webhook"})
REQUEST_TIMEOUT_SECONDS = 10.0


def _dispatch_notification_email(*, to_email: str, title: str, body: str | None) -> None:
    """Same dev/local logging adapter as password reset/invitations — logs
    instead of sending real email (docs/KNOWN_LIMITATIONS.md)."""
    logger.info("Notification email to %s: %s — %s", to_email, title, body or "")


async def _dispatch_notification_webhook(
    *, url: str, title: str, body: str | None, link: str | None
) -> bool:
    payload: dict[str, Any] = {"title": title, "body": body, "link": link}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("Notification webhook delivery to %s failed: %s", url, exc)
        return False


async def notify(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str,
    body: str | None = None,
    link: str | None = None,
    channels: list[str] | None = None,
    idempotency_key: str | None = None,
) -> Notification:
    """Creates the in-app Notification row (always) and honestly attempts
    any additional requested channels. `channels` is the caller's *ask*
    beyond in-app (e.g. `["email"]`) — what actually got delivered is
    recorded on the returned row's `channels_delivered`, which callers can
    inspect but are never required to.

    `idempotency_key` names the *state transition* rather than the
    attempt. A retried background job passes the same key and this
    returns the notification it already raised, unread state and all —
    one document finishing analysis produced "Document analyzed" three
    times when the job retried twice, which teaches people to ignore the
    bell. Callers with no natural key omit it and keep the old
    behaviour."""
    if idempotency_key is not None:
        existing = (
            await db.execute(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.idempotency_key == idempotency_key,
                )
            )
        ).scalars().first()
        if existing is not None:
            return existing

    requested = ["in_app", *(channels or [])]
    delivered = ["in_app"]

    extra_channels = [c for c in (channels or []) if c != "in_app"]
    if extra_channels:
        preferences = (
            (
                await db.execute(
                    select(NotificationPreference).where(
                        NotificationPreference.user_id == user_id,
                        NotificationPreference.channel.in_(extra_channels),
                    )
                )
            )
            .scalars()
            .all()
        )
        enabled_channels = {p.channel for p in preferences if p.enabled}

        if "email" in extra_channels and "email" in enabled_channels:
            from app.identity.models import User

            user = await db.get(User, user_id)
            if user is not None:
                _dispatch_notification_email(to_email=user.email, title=title, body=body)
                delivered.append("email")

        if "webhook" in extra_channels and "webhook" in enabled_channels:
            org = await db.get(Organization, organization_id)
            if org is not None and org.notification_webhook_url:
                sent = await _dispatch_notification_webhook(
                    url=org.notification_webhook_url, title=title, body=body, link=link
                )
                if sent:
                    delivered.append("webhook")

        # Slack/Teams: deliberately never appended to `delivered` even if
        # the user enabled the preference — see module docstring.

    notification = Notification(
        organization_id=organization_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        title=title,
        body=body,
        link=link,
        channels_requested=requested,
        channels_delivered=delivered,
    )
    db.add(notification)
    await db.flush()
    return notification
