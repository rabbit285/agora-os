"""Real HubSpot OAuth2 connector adapter (spec §48's CRM category).

Only instantiated when `HUBSPOT_CLIENT_ID`/`HUBSPOT_CLIENT_SECRET` are
configured (see `app.integrations.service.get_oauth_adapter`) — this
environment has no real HubSpot developer app, so this class is never
exercised end to end here, but every method is a real HTTP call against
HubSpot's documented OAuth/CRM endpoints, not a stub. Read-only CRM scopes
only (spec §B1 progressive trust model, Stage 1).
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
TOKEN_INFO_URL = "https://api.hubapi.com/oauth/v1/access-tokens/{token}"
CONTACTS_URL = "https://api.hubapi.com/crm/v3/objects/contacts"
SCOPES = ["crm.objects.contacts.read", "crm.objects.companies.read"]
DEFAULT_SCOPES = " ".join(SCOPES)
REQUEST_TIMEOUT_SECONDS = 15.0


class HubSpotAdapter:
    provider_key = "hubspot"
    SCOPES = SCOPES

    def __init__(self, *, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        url = httpx.URL(
            AUTHORIZE_URL,
            params={
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "scope": DEFAULT_SCOPES,
                "state": state,
            },
        )
        return str(url)

    async def exchange_code_for_tokens(self, *, code: str, redirect_uri: str) -> TokenResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
            response.raise_for_status()
            body = response.json()
        return TokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in_seconds=body.get("expires_in"),
            scopes=DEFAULT_SCOPES.split(),
        )

    async def refresh_access_token(self, *, refresh_token: str) -> TokenResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            body = response.json()
        return TokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", refresh_token),
            expires_in_seconds=body.get("expires_in"),
            scopes=DEFAULT_SCOPES.split(),
        )

    async def test_connection(self, *, access_token: str) -> HealthResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(TOKEN_INFO_URL.format(token=access_token))
        if response.status_code != 200:
            return HealthResult(
                ok=False, detail=f"HubSpot token check failed (HTTP {response.status_code})"
            )
        body = response.json()
        hub_id = body.get("hub_id")
        return HealthResult(
            ok=True, detail="Connected", external_account_id=str(hub_id) if hub_id else None
        )

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult:
        """Incremental, checkpointed (spec §G2): HubSpot's own `after`
        pagination cursor is round-tripped via `SyncResult.next_cursor` /
        `IntegrationConnection.sync_cursor` so each sync continues from
        where the previous one left off instead of re-fetching the same
        first page of contacts every time."""
        params: dict[str, str | int] = {"limit": 10}
        if cursor:
            params["after"] = cursor
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                CONTACTS_URL,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            body = response.json()
        results = body.get("results", [])
        next_cursor = body.get("paging", {}).get("next", {}).get("after")
        return SyncResult(
            items_synced=len(results),
            detail="Fetched HubSpot contacts (read-only)",
            next_cursor=next_cursor,
        )

    async def revoke(self, *, access_token: str) -> None:
        # HubSpot has no direct access-token revocation endpoint; clearing
        # our own stored copy (done by the caller) is the practical
        # equivalent for this build's purposes.
        return None
