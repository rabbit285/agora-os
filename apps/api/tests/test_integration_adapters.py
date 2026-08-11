"""Unit tests for the provider-neutral OAuth adapter registry
(`app.integrations.adapters`) — pure, no DB/HTTP/client fixture, since
`authorization_url` construction and provider selection are synchronous,
side-effect-free logic. The real token-exchange/health/sync HTTP calls
against each real provider are not exercised here (no live credentials
exist in this environment, same as HubSpot — see
`tests/test_integrations.py` for the mock-adapter-backed integration
tests that do run end to end).
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.integrations.adapters import (
    OAUTH_PROVIDER_KEYS,
    default_redirect_uri,
    get_oauth_adapter,
    is_provider_configured,
    provider_scopes,
)
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

ALL_PROVIDERS = {
    "hubspot",
    "google",
    "microsoft",
    "github",
    "slack",
    "salesforce",
    "zendesk",
    "pipedrive",
    "intercom",
    # The Sales Lead Finder's customer-connected data provider: each
    # organization authorizes its own Apollo workspace (ADR-0064, see
    # docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md). It rides the same
    # provider-neutral OAuth framework as the connectors above.
    "apollo",
}


def test_oauth_provider_keys_match_all_expected_providers() -> None:
    assert OAUTH_PROVIDER_KEYS == ALL_PROVIDERS


@pytest.mark.parametrize("connector_key", sorted(ALL_PROVIDERS))
def test_no_provider_is_configured_without_env_vars(connector_key: str) -> None:
    # No real credentials exist in this test environment for any provider —
    # the registry must report this honestly (spec §82).
    assert is_provider_configured(connector_key) is False


@pytest.mark.parametrize("connector_key", sorted(ALL_PROVIDERS))
def test_unconfigured_provider_falls_back_to_labeled_mock_adapter(connector_key: str) -> None:
    adapter = get_oauth_adapter(connector_key)
    assert isinstance(adapter, MockOAuthAdapter)
    assert adapter.provider_key == connector_key


def test_unknown_connector_key_falls_back_to_generic_mock() -> None:
    adapter = get_oauth_adapter("not-a-real-provider")
    assert isinstance(adapter, MockOAuthAdapter)
    assert adapter.provider_key == "mock"


@pytest.mark.parametrize("connector_key", sorted(ALL_PROVIDERS))
def test_every_provider_exposes_a_nonempty_scope_preview(connector_key: str) -> None:
    scopes = provider_scopes(connector_key)
    assert scopes
    assert all(isinstance(s, str) and s for s in scopes)


def test_unknown_connector_key_has_no_scope_preview() -> None:
    assert provider_scopes("not-a-real-provider") == []


def test_default_redirect_uri_falls_back_to_api_url_pattern() -> None:
    uri = default_redirect_uri("google")
    assert uri.endswith("/api/v1/integrations/connections/oauth/google/callback")


def test_hubspot_authorization_url_includes_client_and_state() -> None:
    adapter = HubSpotAdapter(client_id="hs-client", client_secret="hs-secret")
    url = urlparse(adapter.authorization_url(state="s1", redirect_uri="https://app.example/cb"))
    params = parse_qs(url.query)
    assert params["client_id"] == ["hs-client"]
    assert params["state"] == ["s1"]
    assert params["redirect_uri"] == ["https://app.example/cb"]
    assert "crm.objects.contacts.read" in params["scope"][0]


def test_google_authorization_url_requests_offline_refresh_token() -> None:
    adapter = GoogleAdapter(client_id="g-client", client_secret="g-secret")
    url = urlparse(adapter.authorization_url(state="s2", redirect_uri="https://app.example/cb"))
    params = parse_qs(url.query)
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert params["response_type"] == ["code"]


def test_microsoft_authorization_url_uses_common_tenant() -> None:
    adapter = MicrosoftAdapter(client_id="ms-client", client_secret="ms-secret")
    url = adapter.authorization_url(state="s3", redirect_uri="https://app.example/cb")
    assert url.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize")


def test_github_authorization_url_and_no_refresh_support() -> None:
    adapter = GitHubAdapter(client_id="gh-client", client_secret="gh-secret")
    url = urlparse(adapter.authorization_url(state="s4", redirect_uri="https://app.example/cb"))
    params = parse_qs(url.query)
    assert params["scope"] == ["read:user"]


async def test_github_refresh_raises_because_classic_tokens_never_expire() -> None:
    adapter = GitHubAdapter(client_id="gh-client", client_secret="gh-secret")
    with pytest.raises(RuntimeError, match="cannot be refreshed"):
        await adapter.refresh_access_token(refresh_token="irrelevant")


async def test_slack_refresh_raises_because_non_rotating_tokens_never_expire() -> None:
    adapter = SlackAdapter(client_id="sl-client", client_secret="sl-secret")
    with pytest.raises(RuntimeError, match="cannot be refreshed"):
        await adapter.refresh_access_token(refresh_token="irrelevant")


def test_slack_authorization_url_uses_comma_joined_scopes() -> None:
    adapter = SlackAdapter(client_id="sl-client", client_secret="sl-secret")
    url = urlparse(adapter.authorization_url(state="s5", redirect_uri="https://app.example/cb"))
    params = parse_qs(url.query)
    assert params["scope"] == ["channels:read"]


def test_salesforce_authorization_url_includes_refresh_token_scope() -> None:
    adapter = SalesforceAdapter(client_id="sf-client", client_secret="sf-secret")
    url = urlparse(adapter.authorization_url(state="s6", redirect_uri="https://app.example/cb"))
    params = parse_qs(url.query)
    assert "refresh_token" in params["scope"][0]


def test_zendesk_authorization_url_is_scoped_to_its_subdomain() -> None:
    adapter = ZendeskAdapter(client_id="zd-client", client_secret="zd-secret", subdomain="acme")
    url = urlparse(adapter.authorization_url(state="s7", redirect_uri="https://app.example/cb"))
    params = parse_qs(url.query)
    assert url.hostname == "acme.zendesk.com"
    assert params["client_id"] == ["zd-client"]
    assert params["state"] == ["s7"]


async def test_zendesk_refresh_raises_because_non_rotating_tokens_never_expire() -> None:
    adapter = ZendeskAdapter(client_id="zd-client", client_secret="zd-secret", subdomain="acme")
    with pytest.raises(RuntimeError, match="cannot be refreshed"):
        await adapter.refresh_access_token(refresh_token="irrelevant")


def test_zendesk_is_not_configured_without_a_subdomain_even_with_client_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "zendesk_client_id", "zd-client")
    monkeypatch.setattr(settings, "zendesk_client_secret", "zd-secret")
    monkeypatch.setattr(settings, "zendesk_subdomain", None)
    assert is_provider_configured("zendesk") is False


def test_pipedrive_authorization_url_includes_client_and_state() -> None:
    adapter = PipedriveAdapter(client_id="pd-client", client_secret="pd-secret")
    url = urlparse(adapter.authorization_url(state="s8", redirect_uri="https://app.example/cb"))
    params = parse_qs(url.query)
    assert params["client_id"] == ["pd-client"]
    assert params["state"] == ["s8"]
    assert params["redirect_uri"] == ["https://app.example/cb"]
    assert "deals:read" in params["scope"][0]


def test_intercom_authorization_url_includes_client_and_state() -> None:
    adapter = IntercomAdapter(client_id="ic-client", client_secret="ic-secret")
    url = urlparse(adapter.authorization_url(state="s9", redirect_uri="https://app.example/cb"))
    params = parse_qs(url.query)
    assert params["client_id"] == ["ic-client"]
    assert params["state"] == ["s9"]
    assert params["redirect_uri"] == ["https://app.example/cb"]


async def test_intercom_refresh_raises_because_non_rotating_tokens_never_expire() -> None:
    adapter = IntercomAdapter(client_id="ic-client", client_secret="ic-secret")
    with pytest.raises(RuntimeError, match="cannot be refreshed"):
        await adapter.refresh_access_token(refresh_token="irrelevant")


async def test_mock_adapter_labels_results_with_its_provider_key() -> None:
    adapter = MockOAuthAdapter(provider_key="salesforce")
    health = await adapter.test_connection(access_token="whatever")
    assert health.external_account_id == "mock-salesforce-account-0001"
    assert "salesforce" in health.detail
    assert "provider=salesforce" in adapter.authorization_url(state="s", redirect_uri="r")
