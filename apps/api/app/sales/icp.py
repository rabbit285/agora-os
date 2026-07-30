"""ICP (Ideal Customer Profile) scoring — spec §20 "ICP Builder".

A deterministic, disclosed formula rather than a black-box model: each
`Account` is scored 0-100 against the organization's single `ICPProfile`
on two independent axes (industry match, employee-count fit), each worth
up to 50 points. An org with no saved profile yet gets `icp_score=None`
on every account — never a fabricated default — until it saves one.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sales.models import Account, ICPProfile

INDUSTRY_WEIGHT = 50.0
EMPLOYEE_COUNT_WEIGHT = 50.0


async def get_icp_profile(db: AsyncSession, *, organization_id: uuid.UUID) -> ICPProfile | None:
    result = await db.execute(
        select(ICPProfile).where(ICPProfile.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


def _industry_score(account: Account, profile: ICPProfile) -> float:
    if not profile.target_industries:
        return INDUSTRY_WEIGHT
    if account.industry and account.industry in profile.target_industries:
        return INDUSTRY_WEIGHT
    return 0.0


def _employee_count_score(account: Account, profile: ICPProfile) -> float:
    lo, hi = profile.min_employee_count, profile.max_employee_count
    if lo is None and hi is None:
        return EMPLOYEE_COUNT_WEIGHT
    if account.employee_count is None:
        return 0.0
    lo = lo if lo is not None else 0
    hi = hi if hi is not None else lo
    if lo <= account.employee_count <= hi:
        return EMPLOYEE_COUNT_WEIGHT
    # Linear decay outside the range, scaled to the range width (minimum
    # width of 1 to avoid division by zero for a single-value range).
    distance = (
        lo - account.employee_count
        if account.employee_count < lo
        else (account.employee_count - hi)
    )
    width = max(hi - lo, 1)
    decayed = EMPLOYEE_COUNT_WEIGHT * max(0.0, 1 - (distance / width))
    return round(decayed, 2)


def compute_icp_score(account: Account, profile: ICPProfile) -> float:
    score = _industry_score(account, profile) + _employee_count_score(account, profile)
    return round(min(100.0, max(0.0, score)), 2)


async def rescore_accounts(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """Recompute `icp_score` for every Account in the org against its
    current ICPProfile. Returns the number of accounts rescored. A no-op
    (returns 0) if the org has not saved a profile yet."""
    profile = await get_icp_profile(db, organization_id=organization_id)
    if profile is None:
        return 0

    result = await db.execute(select(Account).where(Account.organization_id == organization_id))
    accounts = list(result.scalars().all())
    for account in accounts:
        account.icp_score = compute_icp_score(account, profile)
    return len(accounts)
