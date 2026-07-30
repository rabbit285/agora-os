"""Lead Finder (spec §21) — finds this organization's own existing
Accounts that fit its ICP but have no open Lead tracking them yet, and
creates one. Deliberately not an external prospecting data source (no
such provider is configured in this build, see
`app.sales.enrichment` for the one piece that does call a real external
API) — Lead Finder here is real value over data the org already has:
surfacing ICP-fit accounts that are falling through the cracks.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sales.icp import get_icp_profile
from app.sales.models import Account, Lead

OPEN_LEAD_STATUSES = ("new", "qualified", "contacted")
MIN_ICP_SCORE_FOR_MATCH = 60.0


async def find_and_create_leads(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> tuple[list[Lead], int]:
    """Returns (newly created Leads, number of candidate Accounts
    considered)."""
    profile = await get_icp_profile(db, organization_id=organization_id)

    accounts_query = select(Account).where(Account.organization_id == organization_id)
    if profile is not None:
        accounts_query = accounts_query.where(Account.icp_score >= MIN_ICP_SCORE_FOR_MATCH)
    accounts = list((await db.execute(accounts_query)).scalars().all())

    existing_leads_result = await db.execute(
        select(Lead.account_id).where(
            Lead.organization_id == organization_id,
            Lead.status.in_(OPEN_LEAD_STATUSES),
            Lead.account_id.isnot(None),
        )
    )
    accounts_with_open_leads = {row[0] for row in existing_leads_result.all()}

    created: list[Lead] = []
    for account in accounts:
        if account.id in accounts_with_open_leads:
            continue
        lead = Lead(
            organization_id=organization_id,
            account_id=account.id,
            source="lead_finder",
            status="new",
            score=account.icp_score,
        )
        db.add(lead)
        created.append(lead)

    if created:
        await db.flush()

    return created, len(accounts)
