"""Sales data-provider status vocabulary — deliberately a separate enum
from `apps.web`'s `IntegrationStatus` / this backend's OAuth
`IntegrationConnection.status`, since the capability shape differs (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §9): a `SalesDataProvider` is
either a single deployment-wide API key (Apollo) or a non-discovery CRM
source (HubSpot/Pipedrive), never a per-organization OAuth connection in
this build.
"""

from __future__ import annotations

from enum import Enum


class SalesProviderStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    # Reserved for a future per-organization credential model — not
    # reachable with today's single deployment-wide APOLLO_API_KEY.
    READY_TO_CONNECT = "ready_to_connect"
    CONNECTED = "connected"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    # Reserved for the future per-organization credential model.
    DISABLED = "disabled"
    REVOKED = "revoked"
    DEMO = "demo"
