"""Per-organization Apollo credential resolution (see
docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md §5).

The Sales Apollo adapter never holds a credential of its own. It is handed
a *resolver* bound to exactly one organization, and asks it for a token
immediately before each outbound call. That keeps three properties true by
construction:

- one organization's token can never serve another's request (the resolver
  is constructed per request, bound to the org from `OrgContext`);
- a decrypted token exists only for the duration of one HTTP call and is
  never stored on the provider, cached, logged, or serialized;
- token refresh happens transparently at the moment of use rather than on
  a schedule that could hand out an expired token.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import utcnow
from app.integrations.models import IntegrationConnection
from app.integrations.service import ensure_fresh_access_token
from app.sales.providers.exceptions import (
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderScopeMissing,
)

# Apollo scope required by each capability (architecture §4). Checked
# *before* a call is attempted, so a missing scope never costs the customer
# credits or fails halfway through a bulk job.
CAPABILITY_SCOPES: dict[str, str] = {
    "search_companies": "mixed_companies_search",
    "search_people": "mixed_people_api_search",
    "find_decision_makers": "mixed_people_api_search",
    "enrich_company": "organizations_enrich",
    "enrich_person": "people_match",
    "usage_stats": "api_usage_stats_read",
}

# A connection in any other state must not be used for live traffic.
USABLE_STATUSES = frozenset({"connected", "healthy", "degraded", "rate_limited"})


@dataclass
class ApolloCredential:
    """A short-lived, single-request credential. Deliberately not cached
    anywhere: `access_token` is decrypted per call and discarded."""

    access_token: str
    connection_id: uuid.UUID
    granted_scopes: list[str]
    # api_key mode only (development/test) — see architecture §7.
    is_legacy_api_key: bool = False


async def get_active_apollo_connection(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> IntegrationConnection | None:
    """This organization's active Apollo connection, or None. Scoped by
    `organization_id` in the query itself — never filtered after the fact."""
    result = await db.execute(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.connector_key == "apollo",
            IntegrationConnection.disconnected_at.is_(None),
        )
        .order_by(IntegrationConnection.created_at.desc())
    )
    return result.scalars().first()


class OrganizationApolloCredentialResolver:
    """Resolves the Apollo credential for exactly one organization."""

    def __init__(self, db: AsyncSession, organization_id: uuid.UUID) -> None:
        self._db = db
        self._organization_id = organization_id

    async def resolve(self, *, capability: str) -> ApolloCredential:
        if settings.apollo_auth_mode == "api_key":
            # Isolated legacy mode for local development/tests only; the
            # startup guard in app.config refuses to run this in
            # production, where a shared key must never serve multiple
            # customers.
            if not settings.apollo_api_key:
                raise ProviderNotConfigured("Apollo is not configured")
            return ApolloCredential(
                access_token=settings.apollo_api_key,
                connection_id=uuid.UUID(int=0),
                granted_scopes=list(CAPABILITY_SCOPES.values()),
                is_legacy_api_key=True,
            )

        connection = await get_active_apollo_connection(
            self._db, organization_id=self._organization_id
        )
        if connection is None or connection.encrypted_access_token is None:
            raise ProviderNotConfigured(
                "This organization has not connected an Apollo workspace"
            )
        if connection.status == "reauthorization_required":
            raise ProviderAuthError(
                "The Apollo connection needs to be authorized again", status_code=401
            )
        if connection.status not in USABLE_STATUSES:
            raise ProviderNotConfigured(
                "This organization's Apollo connection is not active"
            )

        required_scope = CAPABILITY_SCOPES.get(capability)
        granted = connection.scopes or []
        if required_scope is not None and required_scope not in granted:
            raise ProviderScopeMissing(
                "The connected Apollo account did not grant access to this capability",
                required_scope=required_scope,
            )

        access_token = await ensure_fresh_access_token(self._db, connection=connection)
        return ApolloCredential(
            access_token=access_token,
            connection_id=connection.id,
            granted_scopes=list(granted),
        )

    async def record_success(self) -> None:
        connection = await get_active_apollo_connection(
            self._db, organization_id=self._organization_id
        )
        if connection is not None:
            connection.last_success_at = utcnow()

    async def mark_reauthorization_required(self, *, detail: str) -> None:
        connection = await get_active_apollo_connection(
            self._db, organization_id=self._organization_id
        )
        if connection is not None:
            connection.status = "reauthorization_required"
            connection.reauthorization_required_at = utcnow()
            connection.last_error = detail
            connection.last_error_code = "invalid_grant"

    async def refresh_after_unauthorized(self) -> ApolloCredential | None:
        """One safe refresh-and-retry after an eligible 401 (architecture
        §10). Returns a new credential, or None when refresh isn't possible
        — the caller must not retry more than once."""
        connection = await get_active_apollo_connection(
            self._db, organization_id=self._organization_id
        )
        if connection is None or connection.encrypted_refresh_token is None:
            return None
        from app.integrations.service import refresh_connection_token

        try:
            await refresh_connection_token(self._db, connection=connection)
        except ValueError:
            return None
        if connection.encrypted_access_token is None:
            return None
        from app.core.crypto import decrypt_token

        return ApolloCredential(
            access_token=decrypt_token(connection.encrypted_access_token),
            connection_id=connection.id,
            granted_scopes=list(connection.scopes or []),
        )
