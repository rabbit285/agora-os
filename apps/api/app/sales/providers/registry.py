"""Provider registry (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §1, §9).
Mirrors `app.integrations.adapters.__init__`'s registry shape: adding a
new provider later is a new adapter module + one new entry here, never a
change to the service layer, router, or frontend.
"""

from __future__ import annotations

from app.config import settings
from app.sales.providers.base import SalesDataProvider
from app.sales.providers.demo import DemoSalesDataProvider
from app.sales.providers.status import SalesProviderStatus

_DEMO = DemoSalesDataProvider()


def is_apollo_configured() -> bool:
    return bool(settings.apollo_api_key)


def get_provider(provider_key: str = "apollo") -> SalesDataProvider:
    """Returns the real provider when configured, else the Demo provider —
    the same "never a fake live result" fallback used throughout this
    codebase's other optional-credential features."""
    if provider_key == "apollo" and is_apollo_configured():
        from app.sales.providers.apollo import ApolloDataProvider

        assert settings.apollo_api_key is not None
        return ApolloDataProvider(api_key=settings.apollo_api_key)
    return _DEMO


def apollo_status() -> SalesProviderStatus:
    """Static configuration status only — does not make a network call.
    Callers wanting live health should await `get_provider().health()`
    separately (kept apart so listing providers is always a fast, free
    call)."""
    if not is_apollo_configured():
        return SalesProviderStatus.DEMO
    return SalesProviderStatus.CONNECTED


def list_provider_keys() -> list[str]:
    """Providers registered for the Lead Finder's discovery/enrichment
    capability. HubSpot/Pipedrive intentionally excluded here — they exist
    as read-only CRM-sync OAuth connectors (`app.integrations`), not as
    `SalesDataProvider` adapters, since neither exposes company/people
    *search* today (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §17)."""
    return ["apollo"]
