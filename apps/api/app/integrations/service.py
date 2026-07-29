"""Integrations domain services.

`receive_webhook_event` is the cross-module hook this slice ships (spec
§38's "Webhook" trigger type): a verified event on a connection linked to
an active, webhook-triggered Automation workflow starts that workflow via
the existing `app.automation.service.start_run` — Automation's execution
engine is reused, not duplicated (ADR-0024).

Signature verification is HMAC-SHA256 over the raw request body, keyed by
the connection's own secret (`hmac.compare_digest`, constant-time — spec
§H "webhook signature verification"). An unverified or malformed request
is still recorded as a `WebhookEvent` (verified=False) so a misconfigured
sender is diagnosable, but it never reaches the workflow engine.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.automation.models import Workflow
from app.automation.service import start_run
from app.db.base import utcnow
from app.integrations.models import IntegrationConnection, WebhookEvent


def generate_webhook_secret() -> str:
    return secrets.token_hex(32)


def sign_payload(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, raw_body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(sign_payload(secret, raw_body), signature)


async def receive_webhook_event(
    db: AsyncSession,
    *,
    connection: IntegrationConnection,
    raw_body: bytes,
    signature: str | None,
) -> WebhookEvent:
    verified = connection.status == "active" and verify_signature(
        connection.webhook_secret, raw_body, signature
    )

    payload: dict[str, Any] | None
    try:
        payload = json.loads(raw_body) if raw_body else None
    except json.JSONDecodeError:
        payload = None

    event = WebhookEvent(
        organization_id=connection.organization_id,
        connection_id=connection.id,
        verified=verified,
        payload=payload,
    )
    db.add(event)
    await db.flush()

    if not verified:
        connection.last_error = (
            "Connection is disabled" if connection.status != "active" else "Invalid signature"
        )
    else:
        connection.last_synced_at = utcnow()
        connection.last_error = None

        if connection.linked_workflow_id is not None:
            workflow = await db.get(Workflow, connection.linked_workflow_id)
            if (
                workflow is not None
                and workflow.status == "active"
                and workflow.trigger_type == "webhook"
            ):
                if connection.created_by is not None:
                    run = await start_run(
                        db,
                        organization_id=connection.organization_id,
                        workflow=workflow,
                        trigger_payload=payload,
                        actor_user_id=connection.created_by,
                    )
                    event.triggered_run_id = run.id
                else:
                    connection.last_error = (
                        "Cannot trigger linked workflow: connection has no creator "
                        "to attribute the run to"
                    )

    await record_event(
        db,
        organization_id=connection.organization_id,
        actor_user_id=None,
        action="integrations.webhook.received",
        object_type="webhook_event",
        object_id=str(event.id),
        policy_decision="allowed" if verified else "denied",
        after_state={
            "verified": verified,
            "triggered_run_id": str(event.triggered_run_id) if event.triggered_run_id else None,
        },
    )
    return event


async def link_workflow(
    db: AsyncSession,
    *,
    connection: IntegrationConnection,
    workflow: Workflow,
) -> None:
    if workflow.trigger_type != "webhook":
        raise ValueError("Workflow must have trigger_type='webhook' to be linked to a connection")
    connection.linked_workflow_id = workflow.id
