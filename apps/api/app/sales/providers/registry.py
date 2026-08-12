"""Provider registry (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §1, §9
and docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md §5).

Apollo is **customer-connected**: resolution is per organization, because
each organization authorizes its own Apollo workspace and spends its own
credits. An organization with no active connection gets the deterministic,
clearly-labeled demo provider — never another tenant's connection, and
never a shared platform key.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.sales.providers.base import SalesDataProvider
from app.sales.providers.credentials import (
    OrganizationApolloCredentialResolver,
    get_active_apollo_connection,
)
from app.sales.providers.demo import DemoSalesDataProvider
from app.sales.providers.status import SalesProviderStatus

_DEMO = DemoSalesDataProvider()


def is_apollo_oauth_available() -> bool:
    """Whether this deployment can offer Apollo connections at all — i.e.
    whether the Veyntra OAuth application itself is configured. Says
    nothing about whether any particular organization has connected."""
    return bool(settings.apollo_oauth_client_id and settings.apollo_oauth_client_secret)


async def is_apollo_configured(db: AsyncSession, *, organization_id: uuid.UUID) -> bool:
    """Whether *this organization* can run live Apollo traffic."""
    if settings.apollo_auth_mode == "api_key":
        return bool(settings.apollo_api_key)
    connection = await get_active_apollo_connection(db, organization_id=organization_id)
    return connection is not None and connection.encrypted_access_token is not None


async def get_provider(
    db: AsyncSession, *, organization_id: uuid.UUID, provider_key: str = "apollo"
) -> SalesDataProvider:
    """The provider this organization's requests should use. Constructed
    per request and bound to one organization — there is deliberately no
    shared, long-lived Apollo client holding a mutable customer token."""
    if provider_key == "apollo" and await is_apollo_configured(
        db, organization_id=organization_id
    ):
        from app.sales.providers.apollo import ApolloDataProvider

        return ApolloDataProvider(
            credential_resolver=OrganizationApolloCredentialResolver(db, organization_id)
        )
    return _DEMO


async def apollo_status(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> SalesProviderStatus:
    """Static, per-organization configuration status — no network call.
    Callers wanting live health should await `(await get_provider(...)).health()`
    separately (kept apart so listing providers is always a fast, free call)."""
    if settings.apollo_auth_mode == "api_key":
        return (
            SalesProviderStatus.CONNECTED if settings.apollo_api_key else SalesProviderStatus.DEMO
        )
    if not is_apollo_oauth_available():
        # The deployment has no Apollo OAuth application configured, so no
        # organization can connect one yet.
        return SalesProviderStatus.NOT_CONFIGURED

    connection = await get_active_apollo_connection(db, organization_id=organization_id)
    if connection is None or connection.encrypted_access_token is None:
        # Apollo *could* be connected by an authorized user — this is the
        # state the enum reserved for a per-organization credential model.
        return SalesProviderStatus.READY_TO_CONNECT
    if connection.status == "reauthorization_required":
        return SalesProviderStatus.REVOKED
    if connection.status == "rate_limited":
        return SalesProviderStatus.RATE_LIMITED
    if connection.status == "degraded" or connection.health_status == "error":
        return SalesProviderStatus.DEGRADED
    return SalesProviderStatus.CONNECTED


def list_provider_keys() -> list[str]:
    """Providers registered for the Lead Finder's discovery/enrichment
    capability. HubSpot/Pipedrive intentionally excluded here — they exist
    as read-only CRM-sync OAuth connectors (`app.integrations`), not as
    `SalesDataProvider` adapters, since neither exposes company/people
    *search* today (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §17)."""
    return ["apollo"]
