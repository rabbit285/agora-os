from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.automation.models import Workflow
from app.automation.workflow_client import RunStarter, get_run_starter
from app.config import settings
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.integrations.adapters import OAUTH_PROVIDER_KEYS, is_provider_configured, provider_scopes
from app.integrations.models import IntegrationConnection, SyncRun, WebhookEvent
from app.integrations.schemas import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionUpdate,
    OAuthStartResponse,
    ProviderCatalogEntry,
    SyncRunOut,
    WebhookEventOut,
)
from app.integrations.service import (
    check_connection_health,
    create_sync_run,
    disconnect_connection,
    generate_webhook_secret,
    handle_oauth_callback,
    link_workflow,
    receive_webhook_event,
    refresh_connection_token,
    start_oauth_flow,
)
from app.integrations.workflow_client import SyncStarter, get_sync_starter

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

PROVIDER_CATALOG: list[dict[str, str]] = [
    {"connector_key": "webhook", "name": "Webhook", "auth_type": "hmac"},
    {"connector_key": "hubspot", "name": "HubSpot", "auth_type": "oauth2"},
    {"connector_key": "google", "name": "Google", "auth_type": "oauth2"},
    {"connector_key": "microsoft", "name": "Microsoft", "auth_type": "oauth2"},
    {"connector_key": "github", "name": "GitHub", "auth_type": "oauth2"},
    {"connector_key": "slack", "name": "Slack", "auth_type": "oauth2"},
    {"connector_key": "salesforce", "name": "Salesforce", "auth_type": "oauth2"},
    {"connector_key": "zendesk", "name": "Zendesk", "auth_type": "oauth2"},
]


async def _get_org_connection(
    db: AsyncSession, connection_id: uuid.UUID, organization_id: uuid.UUID
) -> IntegrationConnection:
    connection = await db.get(IntegrationConnection, connection_id)
    if connection is None or connection.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return connection


@router.get("/providers", response_model=list[ProviderCatalogEntry])
async def list_providers(
    context: OrgContext = Depends(get_org_context),
) -> list[ProviderCatalogEntry]:
    return [
        ProviderCatalogEntry(
            connector_key=entry["connector_key"],
            name=entry["name"],
            auth_type=entry["auth_type"],
            configured=(
                True
                if entry["connector_key"] == "webhook"
                else is_provider_configured(entry["connector_key"])
            ),
            scopes=provider_scopes(entry["connector_key"]),
        )
        for entry in PROVIDER_CATALOG
    ]


@router.get("/connections", response_model=list[ConnectionOut])
async def list_connections(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[IntegrationConnection]:
    result = await db.execute(
        select(IntegrationConnection)
        .where(IntegrationConnection.organization_id == context.organization_id)
        .order_by(IntegrationConnection.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/connections", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("integrations.connections.manage")),
) -> IntegrationConnection:
    connection = IntegrationConnection(
        organization_id=context.organization_id,
        name=payload.name,
        webhook_secret=generate_webhook_secret(),
        created_by=context.user.id,
    )
    db.add(connection)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="integrations.connection.created",
        object_type="integration_connection",
        object_id=str(connection.id),
        after_state={"name": connection.name, "connector_key": connection.connector_key},
    )
    await db.commit()
    await db.refresh(connection)
    return connection


@router.patch("/connections/{connection_id}", response_model=ConnectionOut)
async def update_connection(
    connection_id: uuid.UUID,
    payload: ConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("integrations.connections.manage")),
) -> IntegrationConnection:
    connection = await _get_org_connection(db, connection_id, context.organization_id)

    if payload.status is not None:
        connection.status = payload.status

    if payload.unlink_workflow:
        connection.linked_workflow_id = None
    elif payload.linked_workflow_id is not None:
        workflow = await db.get(Workflow, payload.linked_workflow_id)
        if workflow is None or workflow.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        try:
            await link_workflow(db, connection=connection, workflow=workflow)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    await db.commit()
    await db.refresh(connection)
    return connection


@router.get("/connections/{connection_id}/events", response_model=list[WebhookEventOut])
async def list_events(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[WebhookEvent]:
    connection = await _get_org_connection(db, connection_id, context.organization_id)
    result = await db.execute(
        select(WebhookEvent)
        .where(WebhookEvent.connection_id == connection.id)
        .order_by(WebhookEvent.received_at.desc())
    )
    return list(result.scalars().all())


@router.post("/connections/oauth/{provider}/start", response_model=OAuthStartResponse)
async def start_oauth(
    provider: str,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("integrations.connections.manage")),
) -> OAuthStartResponse:
    if provider not in OAUTH_PROVIDER_KEYS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")
    connection, authorization_url = await start_oauth_flow(
        db,
        organization_id=context.organization_id,
        connector_key=provider,
        actor_user_id=context.user.id,
    )
    await db.commit()
    return OAuthStartResponse(connection_id=connection.id, authorization_url=authorization_url)


@router.get("/connections/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """No session dependency — this is a top-level browser redirect from the
    provider, not necessarily the tab that started the flow. The `state`
    parameter (not a cookie) is what proves this callback belongs to a
    pending connection, the same "capability token" pattern the webhook
    receiver uses HMAC for."""
    try:
        connection = await handle_oauth_callback(db, state=state, code=code)
    except ValueError as exc:
        await db.rollback()
        return RedirectResponse(
            url=f"{settings.app_url}/settings/integrations?error={quote(str(exc))}"
        )
    await db.commit()
    return RedirectResponse(
        url=f"{settings.app_url}/settings/integrations?connected={connection.connector_key}"
    )


@router.post("/connections/{connection_id}/refresh", response_model=ConnectionOut)
async def refresh_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("integrations.connections.manage")),
) -> IntegrationConnection:
    connection = await _get_org_connection(db, connection_id, context.organization_id)
    try:
        connection = await refresh_connection_token(
            db, connection=connection, actor_user_id=context.user.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(connection)
    return connection


@router.post("/connections/{connection_id}/health", response_model=ConnectionOut)
async def check_health(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("integrations.connections.manage")),
) -> IntegrationConnection:
    connection = await _get_org_connection(db, connection_id, context.organization_id)
    connection = await check_connection_health(db, connection=connection)
    await db.commit()
    await db.refresh(connection)
    return connection


@router.post("/connections/{connection_id}/disconnect", response_model=ConnectionOut)
async def disconnect(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("integrations.connections.manage")),
) -> IntegrationConnection:
    connection = await _get_org_connection(db, connection_id, context.organization_id)
    connection = await disconnect_connection(
        db, connection=connection, actor_user_id=context.user.id
    )
    await db.commit()
    await db.refresh(connection)
    return connection


@router.post("/connections/{connection_id}/sync", response_model=SyncRunOut)
async def sync_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("integrations.connections.manage")),
    start_sync: SyncStarter = Depends(get_sync_starter),
) -> SyncRun:
    """Creates the SyncRun row synchronously (so the response and the
    sync-runs list are consistent immediately) then kicks off
    `IntegrationSyncWorkflow` durably and returns without waiting for it —
    the frontend polls `GET .../sync-runs` for the running -> succeeded/
    failed transition, the same async UX `POST /knowledge/documents`
    uses for ingestion."""
    connection = await _get_org_connection(db, connection_id, context.organization_id)
    sync_run = await create_sync_run(db, connection=connection, actor_user_id=context.user.id)
    await db.commit()
    await db.refresh(sync_run)
    await start_sync(connection.id, sync_run.id)
    return sync_run


@router.get("/connections/{connection_id}/sync-runs", response_model=list[SyncRunOut])
async def list_sync_runs(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[SyncRun]:
    connection = await _get_org_connection(db, connection_id, context.organization_id)
    result = await db.execute(
        select(SyncRun)
        .where(SyncRun.connection_id == connection.id)
        .order_by(SyncRun.started_at.desc())
    )
    return list(result.scalars().all())


@router.post("/webhooks/{connection_id}/receive", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    connection_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    run_starter: RunStarter = Depends(get_run_starter),
) -> dict[str, bool]:
    """No session/OrgContext dependency — the caller is an external system,
    not a logged-in platform user. The security boundary is the HMAC
    signature (`app.integrations.service.verify_signature`), not RBAC."""
    connection = await db.get(IntegrationConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    raw_body = await request.body()
    signature = request.headers.get("X-Webhook-Signature")
    event = await receive_webhook_event(
        db, connection=connection, raw_body=raw_body, signature=signature, run_starter=run_starter
    )
    await db.commit()
    return {"received": True, "verified": event.verified}
