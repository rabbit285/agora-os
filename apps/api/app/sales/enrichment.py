"""Company enrichment (spec §21 "Enrichment") via Clearbit's real Company
API — gated on a real `CLEARBIT_API_KEY`, the same credential-gated
honesty pattern already used for the AI providers, the six OAuth
integrations, and AWS Cloud Security scanning: absent a key, enrichment
returns `configured=False` and changes nothing, never a fabricated
company profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings
from app.sales.models import Account

CLEARBIT_COMPANY_URL = "https://company.clearbit.com/v2/companies/find"


def is_enrichment_configured() -> bool:
    return bool(settings.clearbit_api_key)


@dataclass
class EnrichmentResult:
    configured: bool
    updated_fields: list[str] = field(default_factory=list)


def _domain_from_website(website: str) -> str:
    return website.replace("https://", "").replace("http://", "").split("/")[0].removeprefix("www.")


async def enrich_account(account: Account) -> EnrichmentResult:
    if not is_enrichment_configured():
        return EnrichmentResult(configured=False)
    if not account.website:
        return EnrichmentResult(configured=True, updated_fields=[])

    domain = _domain_from_website(account.website)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            CLEARBIT_COMPANY_URL,
            params={"domain": domain},
            headers={"Authorization": f"Bearer {settings.clearbit_api_key}"},
        )
    if response.status_code != 200:
        return EnrichmentResult(configured=True, updated_fields=[])

    data: dict[str, Any] = response.json()
    updated: list[str] = []

    category = data.get("category") or {}
    industry = category.get("industry")
    if industry and not account.industry:
        account.industry = industry[:100]
        updated.append("industry")

    metrics = data.get("metrics") or {}
    employees = metrics.get("employees")
    if employees and account.employee_count is None:
        account.employee_count = int(employees)
        updated.append("employee_count")

    return EnrichmentResult(configured=True, updated_fields=updated)
