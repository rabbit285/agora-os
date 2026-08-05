"""Natural-language-to-filter parsing for the Lead Finder search bar (see
docs/SALES_LEAD_FINDER_IMPLEMENTATION_PLAN.md Phase 1). Returns
*filters*, never records — the model never sees real provider data and
is never asked to invent a company, person, email, or phone number; it
only translates a sentence into the same structured filter shape the
manual filter sidebar produces, which the user reviews and edits before
anything is searched for real (spec's explicit "AI must not invent
companies/people/titles/emails/..." requirement).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import GenerateRequest, ModelGateway

PROMPT_VERSION = "sales-lead-finder-nl-filter-v1"


class ParsedCompanyFilters(BaseModel):
    industries: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    min_employee_count: int | None = None
    max_employee_count: int | None = None
    keywords: list[str] = Field(default_factory=list)


class ParsedPersonFilters(BaseModel):
    titles: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)
    seniorities: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


class ParsedQuery(BaseModel):
    company_filters: ParsedCompanyFilters
    person_filters: ParsedPersonFilters
    # Criteria the user asked for that this schema has no field for (e.g.
    # "companies that raised a Series B in the last 6 months" has no
    # funding-recency field today) — shown to the user honestly instead
    # of silently dropped.
    unsupported_criteria: list[str] = Field(default_factory=list)


_SCHEMA_DESCRIPTION = """\
company_filters.industries: list of industry names mentioned
company_filters.locations: list of city/country/region names for the company's location
company_filters.min_employee_count / max_employee_count: integers, from phrases like \
"20-200 employees" or "startups under 50 people"
company_filters.keywords: any other company-descriptive keywords (e.g. "B2B SaaS")
person_filters.titles: exact job titles mentioned (e.g. "CEO", "Head of Security")
person_filters.title_keywords: looser title words (e.g. "security", "compliance") when no \
exact title was given
person_filters.seniorities: one or more of: owner, founder, c_suite, vp, director, manager, \
senior, entry
person_filters.departments: department names (e.g. "Engineering", "Legal & Compliance")
person_filters.locations: city/country/region names for the person's own location
unsupported_criteria: any part of the request that doesn't fit the fields above — quote it \
back, don't drop it silently\
"""


def build_parse_request(query: str) -> GenerateRequest:
    """Pure so the prompt shape is unit-testable without a real model
    call (same reasoning as app.ai.copilot.build_grounded_prompt and
    app.ai.gateway.build_rerank_request)."""
    prompt = (
        "Translate the following natural-language sales-prospecting request into "
        "structured search filters. Only extract criteria the user actually stated — "
        "never invent an industry, location, title, or number that wasn't mentioned or "
        "clearly implied. Field meanings:\n\n"
        f"{_SCHEMA_DESCRIPTION}\n\n"
        f'Request: "{query}"'
    )
    return GenerateRequest(
        task_type="sales.lead_finder.parse_query",
        prompt=prompt,
        prompt_version=PROMPT_VERSION,
        input_classification="internal",
    )


async def parse_query(
    db: AsyncSession, *, organization_id: uuid.UUID, requested_by: uuid.UUID, query: str
) -> ParsedQuery:
    gateway = ModelGateway()
    request = build_parse_request(query)
    result = await gateway.generate_structured(
        db,
        organization_id=organization_id,
        requested_by=requested_by,
        request=request,
        schema=ParsedQuery,
    )
    assert isinstance(result, ParsedQuery)
    return result
