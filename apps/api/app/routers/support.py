from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.governance import check_customer_disclosure_permission
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.support.models import CSATResponse, Customer, KnowledgeArticle, Ticket, TicketMessage
from app.support.schemas import (
    CSATResponseCreate,
    CSATResponseOut,
    CustomerCreate,
    CustomerOut,
    KnowledgeArticleCreate,
    KnowledgeArticleOut,
    KnowledgeArticleUpdate,
    TicketCreate,
    TicketDetailOut,
    TicketMessageCreate,
    TicketMessageOut,
    TicketOut,
    TicketUpdate,
)
from app.support.service import create_ticket, flag_upsell_signal

router = APIRouter(prefix="/api/v1/support", tags=["support"])


@router.get("/customers", response_model=list[CustomerOut])
async def list_customers(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Customer]:
    result = await db.execute(
        select(Customer)
        .where(Customer.organization_id == context.organization_id)
        .order_by(Customer.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/customers", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.tickets.manage")),
) -> Customer:
    customer = Customer(organization_id=context.organization_id, **payload.model_dump())
    db.add(customer)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="support.customer.created",
        object_type="support_customer",
        object_id=str(customer.id),
        after_state={"name": customer.name},
    )
    await db.commit()
    await db.refresh(customer)
    return customer


async def _get_org_customer(
    db: AsyncSession, customer_id: uuid.UUID, organization_id: uuid.UUID
) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None or customer.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


async def _get_org_ticket(
    db: AsyncSession, ticket_id: uuid.UUID, organization_id: uuid.UUID
) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


@router.get("/tickets", response_model=list[TicketOut])
async def list_tickets(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Ticket]:
    result = await db.execute(
        select(Ticket)
        .where(Ticket.organization_id == context.organization_id)
        .order_by(Ticket.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket_route(
    payload: TicketCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.tickets.manage")),
) -> Ticket:
    await _get_org_customer(db, payload.customer_id, context.organization_id)
    ticket = await create_ticket(
        db,
        organization_id=context.organization_id,
        customer_id=payload.customer_id,
        subject=payload.subject,
        description=payload.description,
        channel=payload.channel,
        category=payload.category,
        priority=payload.priority,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get("/tickets/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> TicketDetailOut:
    ticket = await _get_org_ticket(db, ticket_id, context.organization_id)
    messages_result = await db.execute(
        select(TicketMessage)
        .where(TicketMessage.ticket_id == ticket.id)
        .order_by(TicketMessage.created_at.asc())
    )
    return TicketDetailOut(
        **TicketOut.model_validate(ticket).model_dump(),
        messages=[TicketMessageOut.model_validate(m) for m in messages_result.scalars().all()],
    )


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.tickets.manage")),
) -> Ticket:
    ticket = await _get_org_ticket(db, ticket_id, context.organization_id)
    before_status = ticket.status
    ticket.status = payload.status
    if payload.status in ("resolved", "closed") and ticket.resolved_at is None:
        ticket.resolved_at = datetime.now(UTC)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="support.ticket.status_changed",
        object_type="support_ticket",
        object_id=str(ticket.id),
        before_state={"status": before_status},
        after_state={"status": ticket.status},
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/flag-upsell", response_model=TicketOut)
async def flag_upsell(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.tickets.manage")),
) -> Ticket:
    ticket = await _get_org_ticket(db, ticket_id, context.organization_id)
    if ticket.upsell_lead_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket is already flagged as an upsell signal",
        )
    customer = await _get_org_customer(db, ticket.customer_id, context.organization_id)
    ticket = await flag_upsell_signal(
        db,
        organization_id=context.organization_id,
        ticket=ticket,
        customer=customer,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=TicketMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket_message(
    ticket_id: uuid.UUID,
    payload: TicketMessageCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.tickets.manage")),
) -> TicketMessage:
    ticket = await _get_org_ticket(db, ticket_id, context.organization_id)

    if payload.sender_type == "agent":
        customer = await _get_org_customer(db, ticket.customer_id, context.organization_id)
        decision = await check_customer_disclosure_permission(
            db, organization_id=context.organization_id, customer=customer
        )
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="support.ticket_message.disclosure_checked",
            object_type="support_ticket",
            object_id=str(ticket.id),
            policy_decision="allowed" if decision.allowed else "denied",
            after_state={"reason": decision.reason} if decision.reason else None,
        )
        if not decision.allowed:
            await db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=decision.reason)

    message = TicketMessage(
        organization_id=context.organization_id,
        ticket_id=ticket.id,
        sender_type=payload.sender_type,
        author_id=context.user.id if payload.sender_type == "agent" else None,
        body=payload.body,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


@router.get("/knowledge-articles", response_model=list[KnowledgeArticleOut])
async def list_knowledge_articles(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[KnowledgeArticle]:
    result = await db.execute(
        select(KnowledgeArticle)
        .where(KnowledgeArticle.organization_id == context.organization_id)
        .order_by(KnowledgeArticle.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/knowledge-articles", response_model=KnowledgeArticleOut, status_code=status.HTTP_201_CREATED
)
async def create_knowledge_article(
    payload: KnowledgeArticleCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.knowledge.manage")),
) -> KnowledgeArticle:
    article = KnowledgeArticle(organization_id=context.organization_id, **payload.model_dump())
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


@router.patch("/knowledge-articles/{article_id}", response_model=KnowledgeArticleOut)
async def update_knowledge_article(
    article_id: uuid.UUID,
    payload: KnowledgeArticleUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.knowledge.manage")),
) -> KnowledgeArticle:
    article = await db.get(KnowledgeArticle, article_id)
    if article is None or article.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    article.published = payload.published
    await db.commit()
    await db.refresh(article)
    return article


@router.post("/csat", response_model=CSATResponseOut, status_code=status.HTTP_201_CREATED)
async def create_csat_response(
    payload: CSATResponseCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> CSATResponse:
    await _get_org_ticket(db, payload.ticket_id, context.organization_id)
    response = CSATResponse(organization_id=context.organization_id, **payload.model_dump())
    db.add(response)
    await db.commit()
    await db.refresh(response)
    return response
