"""Adapter selection — mirrors `app.ai.gateway.build_adapter`: pick the
real provider when it's configured, otherwise fall back to a mock that
never claims to be a live connection (spec §82, §C2).

Every provider is registered here with its adapter class + the three
config values that decide whether it's "configured": adding a seventh
provider later means one new adapter module + one new `_ProviderSpec`
entry + three new environment variables — never a change to the OAuth
flow, the router, the service layer, or the frontend (see
`docs/DECISIONS.md` ADR-0028).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.config import settings
from app.integrations.adapters.apollo import ApolloOAuthAdapter
from app.integrations.adapters.base import OAuthConnectorAdapter
from app.integrations.adapters.github import GitHubAdapter
from app.integrations.adapters.google import GoogleAdapter
from app.integrations.adapters.hubspot import HubSpotAdapter
from app.integrations.adapters.intercom import IntercomAdapter
from app.integrations.adapters.microsoft import MicrosoftAdapter
from app.integrations.adapters.mock import MockOAuthAdapter
from app.integrations.adapters.pipedrive import PipedriveAdapter
from app.integrations.adapters.salesforce import SalesforceAdapter
from app.integrations.adapters.slack import SlackAdapter
from app.integrations.adapters.zendesk import ZendeskAdapter


class _AdapterFactory(Protocol):
    """Every real adapter class, viewed as a callable constructor — a
    Protocol can't otherwise express "callable with these kwargs" for a
    `type[...]` value the way a concrete class's `__init__` can."""

    SCOPES: list[str]

    def __call__(self, *, client_id: str, client_secret: str) -> OAuthConnectorAdapter: ...


@dataclass(frozen=True)
class _ProviderSpec:
    adapter_cls: _AdapterFactory
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    # Zendesk-only (see app.integrations.adapters.zendesk's module
    # docstring): a Zendesk OAuth client is registered against one specific
    # customer subdomain, so it needs a fourth "is this configured" input
    # the other five providers don't.
    subdomain: str | None = None


def _provider_specs() -> dict[str, _ProviderSpec]:
    return {
        "hubspot": _ProviderSpec(
            HubSpotAdapter,
            settings.hubspot_client_id,
            settings.hubspot_client_secret,
            settings.hubspot_redirect_uri,
        ),
        "google": _ProviderSpec(
            GoogleAdapter,
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_redirect_uri,
        ),
        "microsoft": _ProviderSpec(
            MicrosoftAdapter,
            settings.microsoft_client_id,
            settings.microsoft_client_secret,
            settings.microsoft_redirect_uri,
        ),
        "github": _ProviderSpec(
            GitHubAdapter,
            settings.github_client_id,
            settings.github_client_secret,
            settings.github_redirect_uri,
        ),
        "slack": _ProviderSpec(
            SlackAdapter,
            settings.slack_client_id,
            settings.slack_client_secret,
            settings.slack_redirect_uri,
        ),
        "salesforce": _ProviderSpec(
            SalesforceAdapter,
            settings.salesforce_client_id,
            settings.salesforce_client_secret,
            settings.salesforce_redirect_uri,
        ),
        "zendesk": _ProviderSpec(
            ZendeskAdapter,  # type: ignore[arg-type]  # extra required `subdomain` kwarg;
            # get_oauth_adapter() below always special-cases zendesk and never invokes
            # `spec.adapter_cls(client_id=..., client_secret=...)` generically for it.
            settings.zendesk_client_id,
            settings.zendesk_client_secret,
            settings.zendesk_redirect_uri,
            settings.zendesk_subdomain,
        ),
        "pipedrive": _ProviderSpec(
            PipedriveAdapter,
            settings.pipedrive_client_id,
            settings.pipedrive_client_secret,
            settings.pipedrive_redirect_uri,
        ),
        "intercom": _ProviderSpec(
            IntercomAdapter,
            settings.intercom_client_id,
            settings.intercom_client_secret,
            settings.intercom_redirect_uri,
        ),
        # The Sales Lead Finder's customer-connected data provider: each
        # organization authorizes its own Apollo workspace and Agora Origin
        # uses that customer's own account, permissions, limits, and
        # credits — never one shared platform key (see
        # docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md).
        "apollo": _ProviderSpec(
            ApolloOAuthAdapter,
            settings.apollo_oauth_client_id,
            settings.apollo_oauth_client_secret,
            settings.apollo_oauth_redirect_uri,
        ),
    }


OAUTH_PROVIDER_KEYS = frozenset(_provider_specs().keys())


def provider_scopes(connector_key: str) -> list[str]:
    """The scopes a real connection to this provider would request — shown
    to the user as a permission preview before they click Connect, even
    when the provider isn't configured yet (spec's progressive-trust
    transparency principle, §B1)."""
    spec = _provider_specs().get(connector_key)
    if spec is None:
        return []
    return list(spec.adapter_cls.SCOPES)


def is_provider_configured(connector_key: str) -> bool:
    spec = _provider_specs().get(connector_key)
    if spec is None:
        return False
    if connector_key == "zendesk":
        return bool(spec.client_id and spec.client_secret and spec.subdomain)
    return bool(spec.client_id and spec.client_secret)


def default_redirect_uri(connector_key: str) -> str:
    spec = _provider_specs().get(connector_key)
    if spec is not None and spec.redirect_uri:
        return spec.redirect_uri
    return f"{settings.api_url}/api/v1/integrations/connections/oauth/{connector_key}/callback"


def get_oauth_adapter(connector_key: str) -> OAuthConnectorAdapter:
    spec = _provider_specs().get(connector_key)
    if spec is not None and is_provider_configured(connector_key):
        assert spec.client_id is not None
        assert spec.client_secret is not None
        if connector_key == "zendesk":
            assert spec.subdomain is not None
            return ZendeskAdapter(
                client_id=spec.client_id,
                client_secret=spec.client_secret,
                subdomain=spec.subdomain,
            )
        return spec.adapter_cls(client_id=spec.client_id, client_secret=spec.client_secret)
    return MockOAuthAdapter(provider_key=connector_key if spec is not None else "mock")
