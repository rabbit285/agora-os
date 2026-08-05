"""Selective/bulk enrichment for saved Accounts/Contacts (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §16, §20). Mirrors
`app.integrations.service`'s `create_sync_run`/`execute_sync_run`/
`run_sync` three-way split exactly: `create_enrichment_job` writes the
`running` row synchronously (so the frontend sees it immediately),
`execute_enrichment_job` does the real provider work and is directly
callable in tests without a live Temporal worker, and
`run_enrichment_job` composes both for the ≤5-record synchronous path.

Never overwrites a field that already has a value (spec §20: "never
overwrite higher-confidence verified data with lower-confidence data
without a merge policy") — the same fill-only-if-missing rule
`app.sales.enrichment.enrich_account` already uses for Clearbit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.sales.models import Account, Contact
from app.sales.provider_models import (
    SalesEnrichmentJob,
    SalesProviderCreditUsage,
    SalesProviderRecord,
)
from app.sales.providers.registry import get_provider
from app.sales.providers.schemas import (
    CompanyEnrichRequest,
    CreditEstimateRequest,
    PersonEnrichRequest,
)


def _domain_from_website(website: str) -> str:
    return (
        website.replace("https://", "")
        .replace("http://", "")
        .split("/")[0]
        .removeprefix("www.")
    )


async def estimate_enrichment_credits(
    *, provider_key: str, operation: str, record_count: int
) -> int:
    provider = get_provider(provider_key)
    estimate = await provider.estimate_credit_usage(
        CreditEstimateRequest(operation=operation, record_count=record_count)  # type: ignore[arg-type]
    )
    return estimate.estimated_credits


async def create_enrichment_job(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    provider_key: str,
    operation: str,
    requested_by_user_id: uuid.UUID,
    target_record_ids: list[uuid.UUID],
    ip_address: str | None,
    user_agent: str | None,
) -> SalesEnrichmentJob:
    estimated_credits = await estimate_enrichment_credits(
        provider_key=provider_key, operation=operation, record_count=len(target_record_ids)
    )
    job = SalesEnrichmentJob(
        organization_id=organization_id,
        provider=provider_key,
        operation=operation,
        status="running",
        requested_by_user_id=requested_by_user_id,
        target_record_ids=[str(i) for i in target_record_ids],
        estimated_credits=estimated_credits,
        started_at=datetime.now(UTC),
    )
    db.add(job)
    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=requested_by_user_id,
        action="sales.lead_finder.enrichment.started",
        object_type="sales_enrichment_job",
        object_id=str(job.id),
        after_state={"operation": operation, "record_count": len(target_record_ids)},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return job


async def _enrich_one_company(
    db: AsyncSession, *, organization_id: uuid.UUID, account_id: uuid.UUID, provider_key: str
) -> int | None:
    provider = get_provider(provider_key)
    account = await db.get(Account, account_id)
    if account is None or account.organization_id != organization_id:
        raise LookupError(f"Account {account_id} not found")
    if not account.website:
        raise ValueError("Account has no website/domain to enrich against")

    response = await provider.enrich_company(
        CompanyEnrichRequest(organization_id=organization_id, domain=_domain_from_website(account.website))
    )
    if response.company is None:
        raise LookupError("Provider returned no match for this company")

    company = response.company
    if not account.industry and company.industry:
        account.industry = company.industry
    if account.employee_count is None and company.employee_count is not None:
        account.employee_count = company.employee_count

    existing_record = (
        await db.execute(
            select(SalesProviderRecord).where(SalesProviderRecord.linked_account_id == account.id)
        )
    ).scalars().first()
    if existing_record is not None:
        existing_record.last_verified_at = datetime.now(UTC)
        existing_record.enrichment_status = "complete"
        existing_record.raw_payload = company.raw
    else:
        db.add(
            SalesProviderRecord(
                organization_id=organization_id,
                provider=company.provider,
                record_type="company",
                provider_record_id=company.provider_record_id,
                normalized_domain=_domain_from_website(account.website),
                retrieved_at=company.retrieved_at,
                last_verified_at=datetime.now(UTC),
                verification_status="demo" if company.provider == "demo" else "provider_supplied",
                enrichment_status="complete",
                raw_payload=company.raw,
                linked_account_id=account.id,
            )
        )
    return response.credits_used


async def _enrich_one_person(
    db: AsyncSession, *, organization_id: uuid.UUID, contact_id: uuid.UUID, provider_key: str
) -> int | None:
    provider = get_provider(provider_key)
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.organization_id != organization_id:
        raise LookupError(f"Contact {contact_id} not found")

    response = await provider.enrich_person(
        PersonEnrichRequest(organization_id=organization_id, email=contact.email, full_name=contact.full_name)
    )
    if response.person is None:
        raise LookupError("Provider returned no match for this person")

    person = response.person
    if not contact.job_title and person.title:
        contact.job_title = person.title

    existing_record = (
        await db.execute(
            select(SalesProviderRecord).where(SalesProviderRecord.linked_contact_id == contact.id)
        )
    ).scalars().first()
    if existing_record is not None:
        existing_record.last_verified_at = datetime.now(UTC)
        existing_record.enrichment_status = "complete"
        existing_record.raw_payload = person.raw
    else:
        db.add(
            SalesProviderRecord(
                organization_id=organization_id,
                provider=person.provider,
                record_type="person",
                provider_record_id=person.provider_record_id,
                normalized_email=contact.email,
                retrieved_at=person.retrieved_at,
                last_verified_at=datetime.now(UTC),
                verification_status="demo" if person.provider == "demo" else "provider_supplied",
                enrichment_status="complete",
                raw_payload=person.raw,
                linked_contact_id=contact.id,
            )
        )
    return response.credits_used


async def execute_enrichment_job(db: AsyncSession, *, job: SalesEnrichmentJob) -> SalesEnrichmentJob:
    """Idempotency guard: a Temporal activity replay after a crash calls
    this again with the same job row — if it's already been finalized,
    return unchanged rather than re-enriching (and re-billing) the same
    records, the same discipline `execute_sync_run` uses."""
    if job.status != "running":
        return job

    total_actual_credits = 0
    any_actual_reported = False
    error_records: list[dict[str, str]] = []
    succeeded = 0
    failed = 0

    for raw_id in job.target_record_ids:
        record_id = uuid.UUID(raw_id)
        try:
            if job.operation == "enrich_company":
                credits = await _enrich_one_company(
                    db, organization_id=job.organization_id, account_id=record_id, provider_key=job.provider
                )
            elif job.operation == "enrich_person":
                credits = await _enrich_one_person(
                    db, organization_id=job.organization_id, contact_id=record_id, provider_key=job.provider
                )
            else:
                raise ValueError(f"Unsupported enrichment operation: {job.operation}")
            await db.flush()
            if credits is not None:
                total_actual_credits += credits
                any_actual_reported = True
            succeeded += 1
        except Exception as exc:  # noqa: BLE001 - recorded per-record, loop continues
            failed += 1
            error_records.append({"record_id": str(record_id), "error": str(exc)})

    job.succeeded_count = succeeded
    job.failed_count = failed
    job.error_records = error_records
    job.actual_credits = total_actual_credits if any_actual_reported else None
    job.completed_at = datetime.now(UTC)
    job.status = "succeeded" if failed == 0 else ("partial" if succeeded > 0 else "failed")

    db.add(
        SalesProviderCreditUsage(
            organization_id=job.organization_id,
            provider=job.provider,
            operation=job.operation,
            estimated_credits=job.estimated_credits,
            actual_credits=job.actual_credits,
            requested_by_user_id=job.requested_by_user_id,
            source_record_ids=job.target_record_ids,
            succeeded=job.status != "failed",
        )
    )
    await db.flush()
    await record_event(
        db,
        organization_id=job.organization_id,
        actor_user_id=job.requested_by_user_id,
        action=(
            "sales.lead_finder.enrichment.failed"
            if job.status == "failed"
            else "sales.lead_finder.enrichment.completed"
        ),
        object_type="sales_enrichment_job",
        object_id=str(job.id),
        after_state={"status": job.status, "succeeded": succeeded, "failed": failed},
        policy_decision="allowed" if job.status != "failed" else "error",
    )
    return job


async def run_enrichment_job(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    provider_key: str,
    operation: str,
    requested_by_user_id: uuid.UUID,
    target_record_ids: list[uuid.UUID],
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SalesEnrichmentJob:
    """Convenience wrapper for the ≤5-record synchronous path and for
    tests/seed data — the bulk (Temporal) path uses `create_enrichment_job`
    + `SalesBulkEnrichmentWorkflow` instead (see `app.sales.workflow_client`)."""
    job = await create_enrichment_job(
        db,
        organization_id=organization_id,
        provider_key=provider_key,
        operation=operation,
        requested_by_user_id=requested_by_user_id,
        target_record_ids=target_record_ids,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return await execute_enrichment_job(db, job=job)
