from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.automation.models import Workflow
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.integrations.models import IntegrationConnection, WebhookEvent
from app.integrations.schemas import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionUpdate,
    WebhookEventOut,
)
from app.integrations.service import generate_webhook_secret, link_workflow, receive_webhook_event

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


async def _get_org_connection(
    db: AsyncSession, connection_id: uuid.UUID, organization_id: uuid.UUID
) -> IntegrationConnection:
    connection = await db.get(IntegrationConnection, connection_id)
    if connection is None or connection.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return connection


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


@router.post("/webhooks/{connection_id}/receive", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    connection_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
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
        db, connection=connection, raw_body=raw_body, signature=signature
    )
    await db.commit()
    return {"received": True, "verified": event.verified}
