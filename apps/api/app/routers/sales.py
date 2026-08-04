from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.pagination import Pagination, paginate, pagination_params
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.sales.enrichment import enrich_account
from app.sales.icp import compute_icp_score, get_icp_profile, rescore_accounts
from app.sales.intelligence import compute_sales_intelligence
from app.sales.lead_finder import find_and_create_leads
from app.sales.meetings import generate_prep_notes
from app.sales.models import (
    Account,
    Campaign,
    Contact,
    ICPProfile,
    Lead,
    Meeting,
    Opportunity,
    OutreachMessage,
    Sequence,
    SequenceEnrollment,
    SequenceStep,
)
from app.sales.schemas import (
    AccountCreate,
    AccountDetailOut,
    AccountOut,
    CampaignCreate,
    CampaignDetailOut,
    CampaignOut,
    CampaignStatsOut,
    ContactCreate,
    ContactDetailOut,
    ContactOut,
    ContactUpdate,
    EnrichmentResultOut,
    ICPProfileIn,
    ICPProfileOut,
    LeadCreate,
    LeadDetailOut,
    LeadFinderResultOut,
    LeadOut,
    LeadUpdate,
    MeetingCreate,
    MeetingOut,
    MeetingUpdate,
    OpportunityCreate,
    OpportunityDetailOut,
    OpportunityOut,
    OpportunityUpdate,
    OutreachMessageCreate,
    OutreachMessageOut,
    ProcessDueStepsResultOut,
    SalesIntelligenceOut,
    SequenceCreate,
    SequenceDetailOut,
    SequenceEnrollmentOut,
    SequenceEnrollRequest,
    SequenceOut,
    SequenceStepCreate,
    SequenceStepOut,
)
from app.sales.sequences import advance_due_enrollments, enroll_contacts
from app.sales.service import close_opportunity_won, send_outreach_message

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Account]:
    stmt = (
        select(Account)
        .where(Account.organization_id == context.organization_id)
        .order_by(Account.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.accounts.manage")),
) -> Account:
    account = Account(organization_id=context.organization_id, **payload.model_dump())
    db.add(account)
    await db.flush()

    profile = await get_icp_profile(db, organization_id=context.organization_id)
    if profile is not None:
        account.icp_score = compute_icp_score(account, profile)

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
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Contact]:
    stmt = (
        select(Contact)
        .where(Contact.organization_id == context.organization_id)
        .order_by(Contact.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


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


@router.get("/contacts/{contact_id}", response_model=ContactDetailOut)
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> ContactDetailOut:
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    account = await db.get(Account, contact.account_id) if contact.account_id else None
    outreach_result = await db.execute(
        select(OutreachMessage)
        .where(OutreachMessage.contact_id == contact.id)
        .order_by(OutreachMessage.created_at.desc())
    )
    return ContactDetailOut(
        **ContactOut.model_validate(contact).model_dump(),
        account=AccountOut.model_validate(account) if account else None,
        outreach=[OutreachMessageOut.model_validate(m) for m in outreach_result.scalars().all()],
    )


@router.get("/leads", response_model=list[LeadOut])
async def list_leads(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Lead]:
    stmt = (
        select(Lead)
        .where(Lead.organization_id == context.organization_id)
        .order_by(Lead.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.leads.manage")),
) -> Lead:
    lead = Lead(organization_id=context.organization_id, **payload.model_dump())
    db.add(lead)
    await db.flush()

    from app.automation.triggers import dispatch_event

    await dispatch_event(
        db,
        organization_id=context.organization_id,
        trigger_type="new_crm_lead",
        payload={"lead_id": str(lead.id), "source": lead.source},
        actor_user_id=context.user.id,
    )

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


@router.get("/leads/{lead_id}", response_model=LeadDetailOut)
async def get_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> LeadDetailOut:
    lead = await db.get(Lead, lead_id)
    if lead is None or lead.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    account = await db.get(Account, lead.account_id) if lead.account_id else None
    contact = await db.get(Contact, lead.contact_id) if lead.contact_id else None
    return LeadDetailOut(
        **LeadOut.model_validate(lead).model_dump(),
        account=AccountOut.model_validate(account) if account else None,
        contact=ContactOut.model_validate(contact) if contact else None,
    )


@router.post("/leads/find", response_model=LeadFinderResultOut)
async def find_leads(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.leads.manage")),
) -> LeadFinderResultOut:
    """Lead Finder (spec §21): creates a Lead for every existing Account
    that fits the org's ICP (or every account, if no ICP profile is
    saved yet) and has no open Lead already — see
    app.sales.lead_finder."""
    created, considered = await find_and_create_leads(db, organization_id=context.organization_id)
    if created:
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="sales.lead_finder.run",
            object_type="organization",
            object_id=str(context.organization_id),
            after_state={"created_count": len(created), "candidates_considered": considered},
        )
    await db.commit()
    for lead in created:
        await db.refresh(lead)
    return LeadFinderResultOut(created_leads=list(created), candidates_considered=considered)


@router.get("/opportunities", response_model=list[OpportunityOut])
async def list_opportunities(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Opportunity]:
    stmt = (
        select(Opportunity)
        .where(Opportunity.organization_id == context.organization_id)
        .order_by(Opportunity.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


@router.post("/opportunities", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    payload: OpportunityCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.opportunities.manage")),
) -> Opportunity:
    await _get_org_account(db, payload.account_id, context.organization_id)
    opportunity = Opportunity(organization_id=context.organization_id, **payload.model_dump())
    db.add(opportunity)
    await db.flush()
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

    if before_stage != opportunity.stage:
        from app.automation.triggers import dispatch_event

        await dispatch_event(
            db,
            organization_id=context.organization_id,
            trigger_type="crm_stage_change",
            payload={
                "opportunity_id": str(opportunity.id),
                "before_stage": before_stage,
                "stage": opportunity.stage,
            },
            actor_user_id=context.user.id,
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


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityDetailOut)
async def get_opportunity(
    opportunity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> OpportunityDetailOut:
    opportunity = await db.get(Opportunity, opportunity_id)
    if opportunity is None or opportunity.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    account = await _get_org_account(db, opportunity.account_id, context.organization_id)
    return OpportunityDetailOut(
        **OpportunityOut.model_validate(opportunity).model_dump(),
        account=AccountOut.model_validate(account),
    )


@router.post("/accounts/{account_id}/enrich", response_model=EnrichmentResultOut)
async def enrich_account_endpoint(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.accounts.manage")),
) -> EnrichmentResultOut:
    """Company enrichment (spec §21) via Clearbit — see
    app.sales.enrichment for the honest configured=false fallback."""
    account = await _get_org_account(db, account_id, context.organization_id)
    result = await enrich_account(account)
    if result.updated_fields:
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="sales.account.enriched",
            object_type="sales_account",
            object_id=str(account.id),
            after_state={"updated_fields": result.updated_fields},
        )
    await db.commit()
    return EnrichmentResultOut(configured=result.configured, updated_fields=result.updated_fields)


@router.get("/icp-profile", response_model=ICPProfileOut | None)
async def get_icp_profile_endpoint(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> ICPProfile | None:
    return await get_icp_profile(db, organization_id=context.organization_id)


@router.put("/icp-profile", response_model=ICPProfileOut)
async def save_icp_profile(
    payload: ICPProfileIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.icp.manage")),
) -> ICPProfile:
    """ICP Builder (spec §20): upserting the org's single profile
    immediately rescans and rescores every existing Account against it
    — see app.sales.icp."""
    profile = await get_icp_profile(db, organization_id=context.organization_id)
    if profile is None:
        profile = ICPProfile(organization_id=context.organization_id, **payload.model_dump())
        db.add(profile)
    else:
        for field_name, value in payload.model_dump().items():
            setattr(profile, field_name, value)
    await db.flush()

    rescored_count = await rescore_accounts(db, organization_id=context.organization_id)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="sales.icp_profile.saved",
        object_type="sales_icp_profile",
        object_id=str(profile.id),
        after_state={"rescored_accounts": rescored_count},
    )
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/intelligence", response_model=SalesIntelligenceOut)
async def get_sales_intelligence(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> SalesIntelligenceOut:
    data = await compute_sales_intelligence(db, organization_id=context.organization_id)
    data["top_accounts_by_icp_score"] = [
        AccountOut.model_validate(a) for a in data["top_accounts_by_icp_score"]
    ]
    return SalesIntelligenceOut(**data)


@router.get("/inbox", response_model=list[OutreachMessageOut])
async def get_sales_inbox(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[OutreachMessage]:
    """Sales Inbox (spec §24): every outreach message this org has sent
    or attempted, across all contacts, newest first. No real
    email/LinkedIn provider is connected (spec's progressive trust
    model), so this reflects outbound status only, not inbound replies
    — see docs/KNOWN_LIMITATIONS.md."""
    result = await db.execute(
        select(OutreachMessage)
        .where(OutreachMessage.organization_id == context.organization_id)
        .order_by(OutreachMessage.created_at.desc())
    )
    return list(result.scalars().all())


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


async def _get_org_sequence(
    db: AsyncSession, sequence_id: uuid.UUID, organization_id: uuid.UUID
) -> Sequence:
    sequence = await db.get(Sequence, sequence_id)
    if sequence is None or sequence.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence not found")
    return sequence


@router.get("/sequences", response_model=list[SequenceOut])
async def list_sequences(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Sequence]:
    result = await db.execute(
        select(Sequence)
        .where(Sequence.organization_id == context.organization_id)
        .order_by(Sequence.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/sequences", response_model=SequenceOut, status_code=status.HTTP_201_CREATED)
async def create_sequence(
    payload: SequenceCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.sequences.manage")),
) -> Sequence:
    sequence = Sequence(
        organization_id=context.organization_id,
        created_by=context.user.id,
        **payload.model_dump(),
    )
    db.add(sequence)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="sales.sequence.created",
        object_type="sales_sequence",
        object_id=str(sequence.id),
        after_state={"name": sequence.name},
    )
    await db.commit()
    await db.refresh(sequence)
    return sequence


@router.get("/sequences/{sequence_id}", response_model=SequenceDetailOut)
async def get_sequence(
    sequence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> SequenceDetailOut:
    sequence = await _get_org_sequence(db, sequence_id, context.organization_id)

    steps_result = await db.execute(
        select(SequenceStep)
        .where(SequenceStep.sequence_id == sequence.id)
        .order_by(SequenceStep.order_index.asc())
    )
    enrollments_result = await db.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.sequence_id == sequence.id)
    )
    return SequenceDetailOut(
        **SequenceOut.model_validate(sequence).model_dump(),
        steps=[SequenceStepOut.model_validate(s) for s in steps_result.scalars().all()],
        enrollments=[
            SequenceEnrollmentOut.model_validate(e) for e in enrollments_result.scalars().all()
        ],
    )


@router.post(
    "/sequences/{sequence_id}/steps",
    response_model=SequenceStepOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_sequence_step(
    sequence_id: uuid.UUID,
    payload: SequenceStepCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.sequences.manage")),
) -> SequenceStep:
    sequence = await _get_org_sequence(db, sequence_id, context.organization_id)
    existing_count = (
        (await db.execute(select(SequenceStep).where(SequenceStep.sequence_id == sequence.id)))
        .scalars()
        .all()
    )
    step = SequenceStep(
        organization_id=context.organization_id,
        sequence_id=sequence.id,
        order_index=len(existing_count),
        **payload.model_dump(),
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


@router.post("/sequences/{sequence_id}/enroll", response_model=SequenceDetailOut)
async def enroll_in_sequence(
    sequence_id: uuid.UUID,
    payload: SequenceEnrollRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.sequences.manage")),
) -> SequenceDetailOut:
    sequence = await _get_org_sequence(db, sequence_id, context.organization_id)
    for contact_id in payload.contact_ids:
        contact = await db.get(Contact, contact_id)
        if contact is None or contact.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    await enroll_contacts(
        db,
        organization_id=context.organization_id,
        sequence=sequence,
        contact_ids=payload.contact_ids,
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="sales.sequence.contacts_enrolled",
        object_type="sales_sequence",
        object_id=str(sequence.id),
        after_state={"contact_count": len(payload.contact_ids)},
    )
    await db.commit()
    return await get_sequence(sequence_id, db, context)


@router.post("/sequences/process-due-steps", response_model=ProcessDueStepsResultOut)
async def process_due_steps(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.sequences.manage")),
) -> ProcessDueStepsResultOut:
    """Fires every currently-due Sequence/Campaign step (spec §23). A real,
    independently callable action today; the natural home for a periodic
    trigger is the Automation module's Temporal worker once its own
    migration lands — see app.sales.sequences."""
    processed = await advance_due_enrollments(
        db, organization_id=context.organization_id, actor_user_id=context.user.id
    )
    await db.commit()
    return ProcessDueStepsResultOut(processed=processed)


@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Campaign]:
    result = await db.execute(
        select(Campaign)
        .where(Campaign.organization_id == context.organization_id)
        .order_by(Campaign.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.sequences.manage")),
) -> Campaign:
    sequence = await _get_org_sequence(db, payload.sequence_id, context.organization_id)
    for contact_id in payload.contact_ids:
        contact = await db.get(Contact, contact_id)
        if contact is None or contact.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    campaign = Campaign(
        organization_id=context.organization_id,
        name=payload.name,
        sequence_id=sequence.id,
        status="active" if payload.contact_ids else "draft",
        created_by=context.user.id,
    )
    db.add(campaign)
    await db.flush()

    if payload.contact_ids:
        await enroll_contacts(
            db,
            organization_id=context.organization_id,
            sequence=sequence,
            contact_ids=payload.contact_ids,
            campaign_id=campaign.id,
        )

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="sales.campaign.created",
        object_type="sales_campaign",
        object_id=str(campaign.id),
        after_state={"name": campaign.name, "contact_count": len(payload.contact_ids)},
    )
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetailOut)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> CampaignDetailOut:
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or campaign.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    enrollments_result = await db.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.campaign_id == campaign.id)
    )
    enrollments = list(enrollments_result.scalars().all())
    contact_ids = [e.contact_id for e in enrollments]
    messages_result = (
        await db.execute(select(OutreachMessage).where(OutreachMessage.contact_id.in_(contact_ids)))
        if contact_ids
        else None
    )
    messages = list(messages_result.scalars().all()) if messages_result is not None else []

    stats = CampaignStatsOut(
        enrolled=len(enrollments),
        messages_sent=sum(1 for m in messages if m.status == "sent"),
        messages_blocked=sum(1 for m in messages if m.status == "blocked"),
        completed=sum(1 for e in enrollments if e.status == "completed"),
    )
    return CampaignDetailOut(**CampaignOut.model_validate(campaign).model_dump(), stats=stats)


@router.get("/meetings", response_model=list[MeetingOut])
async def list_meetings(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Meeting]:
    result = await db.execute(
        select(Meeting)
        .where(Meeting.organization_id == context.organization_id)
        .order_by(Meeting.scheduled_at.asc())
    )
    return list(result.scalars().all())


@router.post("/meetings", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.meetings.manage")),
) -> Meeting:
    if payload.account_id is not None:
        await _get_org_account(db, payload.account_id, context.organization_id)

    meeting = Meeting(organization_id=context.organization_id, **payload.model_dump())
    db.add(meeting)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="sales.meeting.created",
        object_type="sales_meeting",
        object_id=str(meeting.id),
        after_state={"title": meeting.title},
    )
    await db.commit()
    await db.refresh(meeting)
    return meeting


@router.patch("/meetings/{meeting_id}", response_model=MeetingOut)
async def update_meeting(
    meeting_id: uuid.UUID,
    payload: MeetingUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.meetings.manage")),
) -> Meeting:
    meeting = await db.get(Meeting, meeting_id)
    if meeting is None or meeting.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    meeting.status = payload.status
    await db.commit()
    await db.refresh(meeting)
    return meeting


@router.post("/meetings/{meeting_id}/prep-notes", response_model=MeetingOut)
async def generate_meeting_prep_notes(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.meetings.manage")),
) -> Meeting:
    """Meeting Assistant (spec §26): a real retrieval-grounded AI Copilot
    call, not a template — see app.sales.meetings."""
    meeting = await db.get(Meeting, meeting_id)
    if meeting is None or meeting.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    account = await db.get(Account, meeting.account_id) if meeting.account_id else None
    meeting.prep_notes = await generate_prep_notes(
        db,
        organization_id=context.organization_id,
        meeting=meeting,
        account=account,
        requested_by=context.user.id,
    )
    await db.commit()
    await db.refresh(meeting)
    return meeting
