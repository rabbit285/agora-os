"""Adapter selection — mirrors `app.ai.gateway.build_adapter`: pick the
real provider when it's configured, otherwise fall back to a mock that
never claims to be a live connection (spec §82, §C2)."""

from __future__ import annotations

from app.config import settings
from app.integrations.adapters.base import OAuthConnectorAdapter
from app.integrations.adapters.mock import MockOAuthAdapter

OAUTH_PROVIDER_KEYS = {"hubspot"}


def is_provider_configured(connector_key: str) -> bool:
    if connector_key == "hubspot":
        return bool(settings.hubspot_client_id and settings.hubspot_client_secret)
    return False


def get_oauth_adapter(connector_key: str) -> OAuthConnectorAdapter:
    if connector_key == "hubspot" and is_provider_configured("hubspot"):
        from app.integrations.adapters.hubspot import HubSpotAdapter

        assert settings.hubspot_client_id is not None
        assert settings.hubspot_client_secret is not None
        return HubSpotAdapter(
            client_id=settings.hubspot_client_id, client_secret=settings.hubspot_client_secret
        )
    return MockOAuthAdapter()
