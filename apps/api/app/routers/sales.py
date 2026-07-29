from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.sales.models import Account, Contact, Lead, Opportunity, OutreachMessage
from app.sales.schemas import (
    AccountCreate,
    AccountDetailOut,
    AccountOut,
    ContactCreate,
    ContactOut,
    ContactUpdate,
    LeadCreate,
    LeadOut,
    LeadUpdate,
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
    OutreachMessageCreate,
    OutreachMessageOut,
)
from app.sales.service import close_opportunity_won, send_outreach_message

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Account]:
    result = await db.execute(
        select(Account)
        .where(Account.organization_id == context.organization_id)
        .order_by(Account.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.accounts.manage")),
) -> Account:
    account = Account(organization_id=context.organization_id, **payload.model_dump())
    db.add(account)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="sales.account.created",
        object_type="sales_account",
        object_id=str(account.id),
        after_state={"name": account.name},
    )
    await db.commit()
    await db.refresh(account)
    return account


async def _get_org_account(
    db: AsyncSession, account_id: uuid.UUID, organization_id: uuid.UUID
) -> Account:
    account = await db.get(Account, account_id)
    if account is None or account.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.get("/accounts/{account_id}", response_model=AccountDetailOut)
async def get_account(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> AccountDetailOut:
    account = await _get_org_account(db, account_id, context.organization_id)

    contacts_result = await db.execute(select(Contact).where(Contact.account_id == account.id))
    opportunities_result = await db.execute(
        select(Opportunity).where(Opportunity.account_id == account.id)
    )

    return AccountDetailOut(
        **AccountOut.model_validate(account).model_dump(),
        contacts=[ContactOut.model_validate(c) for c in contacts_result.scalars().all()],
        opportunities=[
            OpportunityOut.model_validate(o) for o in opportunities_result.scalars().all()
        ],
    )


@router.get("/contacts", response_model=list[ContactOut])
async def list_contacts(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Contact]:
    result = await db.execute(
        select(Contact)
        .where(Contact.organization_id == context.organization_id)
        .order_by(Contact.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.accounts.manage")),
) -> Contact:
    if payload.account_id is not None:
        await _get_org_account(db, payload.account_id, context.organization_id)

    contact = Contact(organization_id=context.organization_id, **payload.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.accounts.manage")),
) -> Contact:
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    contact.do_not_contact = payload.do_not_contact
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="sales.contact.suppression_updated",
        object_type="sales_contact",
        object_id=str(contact.id),
        after_state={"do_not_contact": contact.do_not_contact},
    )
    await db.commit()
    await db.refresh(contact)
    return contact


@router.get("/leads", response_model=list[LeadOut])
async def list_leads(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Lead]:
    result = await db.execute(
        select(Lead)
        .where(Lead.organization_id == context.organization_id)
        .order_by(Lead.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.leads.manage")),
) -> Lead:
    lead = Lead(organization_id=context.organization_id, **payload.model_dump())
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.patch("/leads/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.leads.manage")),
) -> Lead:
    lead = await db.get(Lead, lead_id)
    if lead is None or lead.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    lead.status = payload.status
    await db.commit()
    await db.refresh(lead)
    return lead


@router.get("/opportunities", response_model=list[OpportunityOut])
async def list_opportunities(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Opportunity]:
    result = await db.execute(
        select(Opportunity)
        .where(Opportunity.organization_id == context.organization_id)
        .order_by(Opportunity.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/opportunities", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    payload: OpportunityCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.opportunities.manage")),
) -> Opportunity:
    await _get_org_account(db, payload.account_id, context.organization_id)
    opportunity = Opportunity(organization_id=context.organization_id, **payload.model_dump())
    db.add(opportunity)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="sales.opportunity.created",
        object_type="sales_opportunity",
        object_id=str(opportunity.id),
        after_state={"title": opportunity.title, "stage": opportunity.stage},
    )
    await db.commit()
    await db.refresh(opportunity)
    return opportunity


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityOut)
async def update_opportunity(
    opportunity_id: uuid.UUID,
    payload: OpportunityUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.opportunities.manage")),
) -> Opportunity:
    opportunity = await db.get(Opportunity, opportunity_id)
    if opportunity is None or opportunity.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    before_stage = opportunity.stage
    opportunity.stage = payload.stage
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="sales.opportunity.stage_changed",
        object_type="sales_opportunity",
        object_id=str(opportunity.id),
        before_state={"stage": before_stage},
        after_state={"stage": opportunity.stage},
    )

    if before_stage != "closed_won" and opportunity.stage == "closed_won":
        account = await _get_org_account(db, opportunity.account_id, context.organization_id)
        opportunity = await close_opportunity_won(
            db,
            organization_id=context.organization_id,
            opportunity=opportunity,
            account=account,
            actor_user_id=context.user.id,
        )

    await db.commit()
    await db.refresh(opportunity)
    return opportunity


@router.get("/outreach", response_model=list[OutreachMessageOut])
async def list_outreach(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[OutreachMessage]:
    result = await db.execute(
        select(OutreachMessage)
        .where(OutreachMessage.organization_id == context.organization_id)
        .order_by(OutreachMessage.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/outreach", response_model=OutreachMessageOut, status_code=status.HTTP_201_CREATED)
async def create_outreach(
    payload: OutreachMessageCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.outreach.manage")),
) -> OutreachMessage:
    contact = await db.get(Contact, payload.contact_id)
    if contact is None or contact.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    message = OutreachMessage(
        organization_id=context.organization_id,
        created_by=context.user.id,
        **payload.model_dump(),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


@router.post("/outreach/{message_id}/send", response_model=OutreachMessageOut)
async def send_outreach(
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.outreach.manage")),
) -> OutreachMessage:
    message = await db.get(OutreachMessage, message_id)
    if message is None or message.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if message.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Message already sent or blocked"
        )
    contact = await db.get(Contact, message.contact_id)
    assert contact is not None  # FK guarantees existence

    message = await send_outreach_message(
        db,
        organization_id=context.organization_id,
        message=message,
        contact=contact,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(message)
    return message
