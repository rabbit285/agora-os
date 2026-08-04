from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.governance import check_customer_disclosure_permission
from app.core.pagination import Pagination, paginate, pagination_params
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.support.analytics import compute_support_analytics
from app.support.copilot import draft_ticket_reply, get_ai_agent_config
from app.support.models import (
    AIAgentConfig,
    CSATResponse,
    Customer,
    KnowledgeArticle,
    Ticket,
    TicketMessage,
    TicketQAScore,
)
from app.support.schemas import (
    AIAgentConfigIn,
    AIAgentConfigOut,
    CSATResponseCreate,
    CSATResponseOut,
    CustomerCreate,
    CustomerOut,
    KnowledgeArticleCreate,
    KnowledgeArticleOut,
    KnowledgeArticleUpdate,
    QAScoreCreate,
    QAScoreOut,
    SupportAnalyticsOut,
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
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Customer]:
    stmt = (
        select(Customer)
        .where(Customer.organization_id == context.organization_id)
        .order_by(Customer.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


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
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Ticket]:
    stmt = (
        select(Ticket)
        .where(Ticket.organization_id == context.organization_id)
        .order_by(Ticket.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


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

    from app.automation.triggers import dispatch_event

    await dispatch_event(
        db,
        organization_id=context.organization_id,
        trigger_type="new_support_ticket",
        payload={
            "ticket_id": str(ticket.id),
            "subject": ticket.subject,
            "category": ticket.category,
        },
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


@router.post("/tickets/{ticket_id}/draft-reply", response_model=TicketMessageOut)
async def draft_reply(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.tickets.manage")),
) -> TicketMessage:
    """AI-grounded ticket response (spec §32): a real retrieval-grounded
    Copilot call, landing as a pending draft unless the org's AI Agent
    is configured to auto-send grounded replies — see
    app.support.copilot."""
    ticket = await _get_org_ticket(db, ticket_id, context.organization_id)
    message = await draft_ticket_reply(
        db, organization_id=context.organization_id, ticket=ticket, requested_by=context.user.id
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="support.ticket_message.ai_drafted",
        object_type="support_ticket",
        object_id=str(ticket.id),
        after_state={"message_id": str(message.id), "status": message.status},
    )
    await db.commit()
    await db.refresh(message)
    return message


@router.post("/tickets/{ticket_id}/messages/{message_id}/send", response_model=TicketMessageOut)
async def send_draft_message(
    ticket_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.tickets.manage")),
) -> TicketMessage:
    """Human approval gate for an AI-drafted reply (spec §32) — never
    auto-sent without either this explicit approval or the org's AI
    Agent config opting in."""
    message = await db.get(TicketMessage, message_id)
    if (
        message is None
        or message.organization_id != context.organization_id
        or message.ticket_id != ticket_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if message.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Message already sent")
    message.status = "sent"
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="support.ticket_message.draft_approved",
        object_type="support_ticket",
        object_id=str(ticket_id),
        after_state={"message_id": str(message.id)},
    )
    await db.commit()
    await db.refresh(message)
    return message


@router.get("/ai-agent-config", response_model=AIAgentConfigOut | None)
async def get_ai_agent_config_endpoint(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> AIAgentConfig | None:
    return await get_ai_agent_config(db, organization_id=context.organization_id)


@router.put("/ai-agent-config", response_model=AIAgentConfigOut)
async def save_ai_agent_config(
    payload: AIAgentConfigIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.ai_agent.manage")),
) -> AIAgentConfig:
    config = await get_ai_agent_config(db, organization_id=context.organization_id)
    if config is None:
        config = AIAgentConfig(organization_id=context.organization_id, **payload.model_dump())
        db.add(config)
    else:
        for field_name, value in payload.model_dump().items():
            setattr(config, field_name, value)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="support.ai_agent_config.saved",
        object_type="support_ai_agent_config",
        object_id=str(config.id),
        after_state=payload.model_dump(),
    )
    await db.commit()
    await db.refresh(config)
    return config


@router.post(
    "/tickets/{ticket_id}/qa-score", response_model=QAScoreOut, status_code=status.HTTP_201_CREATED
)
async def create_qa_score(
    ticket_id: uuid.UUID,
    payload: QAScoreCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("support.qa.manage")),
) -> TicketQAScore:
    await _get_org_ticket(db, ticket_id, context.organization_id)
    qa_score = TicketQAScore(
        organization_id=context.organization_id,
        ticket_id=ticket_id,
        reviewer_id=context.user.id,
        **payload.model_dump(),
    )
    db.add(qa_score)
    await db.commit()
    await db.refresh(qa_score)
    return qa_score


@router.get("/tickets/{ticket_id}/qa-scores", response_model=list[QAScoreOut])
async def list_qa_scores(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[TicketQAScore]:
    await _get_org_ticket(db, ticket_id, context.organization_id)
    result = await db.execute(
        select(TicketQAScore)
        .where(TicketQAScore.ticket_id == ticket_id)
        .order_by(TicketQAScore.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/analytics", response_model=SupportAnalyticsOut)
async def get_support_analytics(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> SupportAnalyticsOut:
    data = await compute_support_analytics(db, organization_id=context.organization_id)
    return SupportAnalyticsOut(**data)


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
