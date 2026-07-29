"""Integrations domain services.

`receive_webhook_event` is the Webhook connector's cross-module hook
(spec §38's "Webhook" trigger type): a verified event on a connection
linked to an active, webhook-triggered Automation workflow starts that
workflow via the existing `app.automation.service.start_run` —
Automation's execution engine is reused, not duplicated (ADR-0024).

Signature verification is HMAC-SHA256 over the raw request body, keyed by
the connection's own secret (`hmac.compare_digest`, constant-time — spec
§H "webhook signature verification"). An unverified or malformed request
is still recorded as a `WebhookEvent` (verified=False) so a misconfigured
sender is diagnosable, but it never reaches the workflow engine.

`start_oauth_flow` / `handle_oauth_callback` / `refresh_connection_token`
/ `check_connection_health` / `disconnect_connection` /
`create_sync_run` + `execute_sync_run` implement the second connector
shape — a real OAuth2 authorization-code flow (spec §49's Connector
Contract) behind a provider-neutral adapter registry (six providers:
HubSpot, Google, Microsoft, GitHub, Slack, Salesforce — ADR-0026,
ADR-0028). `oauth_state` is this flow's own "capability token": the
callback route has no session (the redirect comes from the provider, not
necessarily the tab that started the flow), so the state parameter alone
— not a cookie — proves which pending connection a callback belongs to,
the same pattern `receive_webhook_event`'s HMAC signature plays for the
webhook connector.

Sync runs as a durable Temporal job (`IntegrationSyncWorkflow`), not
inline in the request: `create_sync_run` writes the `running` row and
returns immediately (called from the router), `execute_sync_run` does the
actual provider call and is invoked by the Temporal activity — the same
request/durable-execution split `app.knowledge.workflow_client` uses for
document ingestion. `run_sync` composes both for tests/seed data that want
a synchronous result without a live Temporal connection.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.automation.models import Workflow
from app.automation.service import start_run
from app.core.crypto import decrypt_token, encrypt_token
from app.db.base import as_aware_utc, utcnow
from app.integrations.adapters import default_redirect_uri, get_oauth_adapter
from app.integrations.models import IntegrationConnection, SyncRun, WebhookEvent

OAUTH_STATE_TTL_SECONDS = 600


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
    verified = (
        connection.status == "active"
        and connection.webhook_secret is not None
        and verify_signature(connection.webhook_secret, raw_body, signature)
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


def oauth_redirect_uri(connector_key: str) -> str:
    return default_redirect_uri(connector_key)


async def start_oauth_flow(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connector_key: str,
    actor_user_id: uuid.UUID,
) -> tuple[IntegrationConnection, str]:
    adapter = get_oauth_adapter(connector_key)
    state = secrets.token_urlsafe(32)

    connection = IntegrationConnection(
        organization_id=organization_id,
        connector_key=connector_key,
        name=connector_key.capitalize(),
        status="not_connected",
        oauth_state=state,
        oauth_state_created_at=utcnow(),
        created_by=actor_user_id,
    )
    db.add(connection)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="integrations.oauth.started",
        object_type="integration_connection",
        object_id=str(connection.id),
        after_state={"connector_key": connector_key},
    )

    authorization_url = adapter.authorization_url(
        state=state, redirect_uri=oauth_redirect_uri(connector_key)
    )
    return connection, authorization_url


async def handle_oauth_callback(
    db: AsyncSession, *, state: str, code: str
) -> IntegrationConnection:
    connection = (
        await db.execute(
            select(IntegrationConnection).where(IntegrationConnection.oauth_state == state)
        )
    ).scalar_one_or_none()
    if connection is None:
        raise ValueError("Unknown or already-used OAuth state")
    if (
        connection.oauth_state_created_at is None
        or (utcnow() - as_aware_utc(connection.oauth_state_created_at)).total_seconds()
        > OAUTH_STATE_TTL_SECONDS
    ):
        raise ValueError("OAuth state has expired — start the connection again")

    adapter = get_oauth_adapter(connection.connector_key)
    redirect_uri = oauth_redirect_uri(connection.connector_key)
    tokens = await adapter.exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)

    connection.encrypted_access_token = encrypt_token(tokens.access_token)
    connection.encrypted_refresh_token = (
        encrypt_token(tokens.refresh_token) if tokens.refresh_token else None
    )
    connection.token_expires_at = (
        utcnow() + timedelta(seconds=tokens.expires_in_seconds)
        if tokens.expires_in_seconds
        else None
    )
    connection.scopes = tokens.scopes
    connection.oauth_state = None
    connection.oauth_state_created_at = None
    connection.status = "connected"

    health = await adapter.test_connection(access_token=tokens.access_token)
    connection.health_status = "ok" if health.ok else "error"
    connection.last_health_check_at = utcnow()
    connection.external_account_id = health.external_account_id

    await record_event(
        db,
        organization_id=connection.organization_id,
        actor_user_id=connection.created_by,
        action="integrations.oauth.connected",
        object_type="integration_connection",
        object_id=str(connection.id),
        after_state={
            "connector_key": connection.connector_key,
            "external_account_id": connection.external_account_id,
        },
    )
    return connection


async def ensure_fresh_access_token(db: AsyncSession, *, connection: IntegrationConnection) -> str:
    """Returns a usable access token, refreshing first if it's expired or
    about to expire. Used internally by health checks and sync so callers
    never have to think about token lifetime themselves."""
    if connection.encrypted_access_token is None:
        raise ValueError("Connection has no stored access token")

    needs_refresh = connection.token_expires_at is not None and as_aware_utc(
        connection.token_expires_at
    ) <= utcnow() + timedelta(minutes=5)

    if needs_refresh and connection.encrypted_refresh_token is not None:
        await refresh_connection_token(db, connection=connection)

    assert connection.encrypted_access_token is not None
    return decrypt_token(connection.encrypted_access_token)


async def refresh_connection_token(
    db: AsyncSession,
    *,
    connection: IntegrationConnection,
    actor_user_id: uuid.UUID | None = None,
) -> IntegrationConnection:
    if connection.encrypted_refresh_token is None:
        raise ValueError("Connection has no refresh token to use")

    adapter = get_oauth_adapter(connection.connector_key)
    refresh_token = decrypt_token(connection.encrypted_refresh_token)
    try:
        tokens = await adapter.refresh_access_token(refresh_token=refresh_token)
    except Exception as exc:  # noqa: BLE001 - normalized to ValueError + audited below
        connection.last_error = str(exc)
        await record_event(
            db,
            organization_id=connection.organization_id,
            actor_user_id=actor_user_id,
            action="integrations.oauth.refresh_failed",
            object_type="integration_connection",
            object_id=str(connection.id),
            policy_decision="denied",
            after_state={"error": str(exc)},
        )
        raise ValueError(f"Token refresh failed: {exc}") from exc

    connection.encrypted_access_token = encrypt_token(tokens.access_token)
    if tokens.refresh_token:
        connection.encrypted_refresh_token = encrypt_token(tokens.refresh_token)
    connection.token_expires_at = (
        utcnow() + timedelta(seconds=tokens.expires_in_seconds)
        if tokens.expires_in_seconds
        else None
    )
    connection.last_error = None
    await record_event(
        db,
        organization_id=connection.organization_id,
        actor_user_id=actor_user_id,
        action="integrations.oauth.refreshed",
        object_type="integration_connection",
        object_id=str(connection.id),
    )
    return connection


async def check_connection_health(
    db: AsyncSession, *, connection: IntegrationConnection
) -> IntegrationConnection:
    if connection.encrypted_access_token is None:
        connection.health_status = "error"
        connection.last_error = "Not connected"
        connection.last_health_check_at = utcnow()
        return connection

    adapter = get_oauth_adapter(connection.connector_key)
    try:
        access_token = await ensure_fresh_access_token(db, connection=connection)
        health = await adapter.test_connection(access_token=access_token)
    except Exception as exc:  # noqa: BLE001 - recorded on the connection, not re-raised
        connection.health_status = "error"
        connection.last_error = str(exc)
        connection.last_health_check_at = utcnow()
        return connection

    connection.health_status = "ok" if health.ok else "error"
    connection.last_error = None if health.ok else health.detail
    connection.last_health_check_at = utcnow()
    if health.external_account_id:
        connection.external_account_id = health.external_account_id
    return connection


async def disconnect_connection(
    db: AsyncSession,
    *,
    connection: IntegrationConnection,
    actor_user_id: uuid.UUID | None = None,
) -> IntegrationConnection:
    revoke_error: str | None = None
    if connection.encrypted_access_token is not None:
        adapter = get_oauth_adapter(connection.connector_key)
        try:
            access_token = decrypt_token(connection.encrypted_access_token)
            await adapter.revoke(access_token=access_token)
        except Exception as exc:  # noqa: BLE001 - best-effort revoke; tokens are cleared regardless
            revoke_error = str(exc)

    connection.encrypted_access_token = None
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.scopes = None
    connection.status = "disconnected"
    connection.health_status = None
    connection.last_error = (
        f"Revoke request failed (tokens cleared locally): {revoke_error}" if revoke_error else None
    )

    await record_event(
        db,
        organization_id=connection.organization_id,
        actor_user_id=actor_user_id,
        action="integrations.oauth.disconnected",
        object_type="integration_connection",
        object_id=str(connection.id),
        policy_decision="denied" if revoke_error else "allowed",
        after_state={"revoke_error": revoke_error} if revoke_error else None,
    )
    return connection


async def create_sync_run(
    db: AsyncSession,
    *,
    connection: IntegrationConnection,
    actor_user_id: uuid.UUID | None = None,
) -> SyncRun:
    """Creates the SyncRun row and records the audit trail entry for the
    request; the actual provider call happens in `execute_sync_run`, run
    from a durable Temporal workflow (`IntegrationSyncWorkflow`) rather than
    inline in the request — see `apps/worker/worker/workflows.py` and
    `docs/DECISIONS.md` ADR-0028. Split into two functions so tests can
    exercise the real adapter logic (`execute_sync_run`) without requiring
    a live Temporal connection, the same pattern
    `app.knowledge.service.ingest_document` uses relative to
    `DocumentIngestionWorkflow`."""
    sync_run = SyncRun(
        organization_id=connection.organization_id,
        connection_id=connection.id,
        status="running",
    )
    db.add(sync_run)
    await db.flush()
    await record_event(
        db,
        organization_id=connection.organization_id,
        actor_user_id=actor_user_id,
        action="integrations.sync.started",
        object_type="integration_sync_run",
        object_id=str(sync_run.id),
        after_state={"connection_id": str(connection.id)},
    )
    return sync_run


async def execute_sync_run(
    db: AsyncSession,
    *,
    connection: IntegrationConnection,
    sync_run: SyncRun,
    actor_user_id: uuid.UUID | None = None,
) -> SyncRun:
    """Runs the actual provider sync call and finalizes `sync_run` — a real
    but deliberately simplified version of spec §49's `sync()` capability
    (no incremental cursors/checkpointing yet, see
    docs/KNOWN_LIMITATIONS.md). Called by the Temporal activity in
    production; called directly in tests."""
    try:
        access_token = await ensure_fresh_access_token(db, connection=connection)
        adapter = get_oauth_adapter(connection.connector_key)
        result = await adapter.sync(access_token=access_token)
        sync_run.status = "succeeded"
        sync_run.items_synced = result.items_synced
        connection.last_synced_at = utcnow()
        connection.last_error = None
        await record_event(
            db,
            organization_id=connection.organization_id,
            actor_user_id=actor_user_id,
            action="integrations.sync.succeeded",
            object_type="integration_sync_run",
            object_id=str(sync_run.id),
            after_state={"items_synced": result.items_synced},
        )
    except Exception as exc:  # noqa: BLE001 - recorded on the SyncRun, not re-raised to the caller
        sync_run.status = "failed"
        sync_run.error = str(exc)
        connection.last_error = str(exc)
        await record_event(
            db,
            organization_id=connection.organization_id,
            actor_user_id=actor_user_id,
            action="integrations.sync.failed",
            object_type="integration_sync_run",
            object_id=str(sync_run.id),
            policy_decision="denied",
            after_state={"error": str(exc)},
        )

    sync_run.completed_at = utcnow()
    return sync_run


async def run_sync(
    db: AsyncSession, *, connection: IntegrationConnection, actor_user_id: uuid.UUID | None = None
) -> SyncRun:
    """Convenience wrapper used only by tests/seed data that want a
    synchronous, single-call sync without going through Temporal — the
    `/connections/{id}/sync` endpoint uses `create_sync_run` +
    `IntegrationSyncWorkflow` instead (see `app.routers.integrations`)."""
    sync_run = await create_sync_run(db, connection=connection, actor_user_id=actor_user_id)
    return await execute_sync_run(
        db, connection=connection, sync_run=sync_run, actor_user_id=actor_user_id
    )
