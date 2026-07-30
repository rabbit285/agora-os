"""Real Zendesk OAuth2 connector adapter (spec §48's Customer Support
category).

Only instantiated when `ZENDESK_CLIENT_ID`/`ZENDESK_CLIENT_SECRET`/
`ZENDESK_SUBDOMAIN` are all configured — this environment has no real
Zendesk account, so this class is never exercised end to end here, but
every method is a real HTTP call against Zendesk's documented OAuth/API v2
endpoints, not a stub.

Known simplification (see docs/KNOWN_LIMITATIONS.md): unlike the other five
providers, a Zendesk OAuth client is registered against one specific
customer subdomain (`https://{subdomain}.zendesk.com`) — there is no
single multi-tenant authorize URL the way HubSpot/Google/Microsoft have.
This build therefore supports exactly one configured Zendesk account
(`settings.zendesk_subdomain`) rather than a per-connection "enter your
Zendesk subdomain" prompt a production build would add before starting the
OAuth flow.

Zendesk OAuth access tokens do not expire under the standard (non-rotating)
grant configuration, so — like GitHub/Slack's classic token models — there
is genuinely no refresh flow to call. Scope is read-only ticket/user
metadata only (spec §B1 progressive trust model, Stage 1).
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

SCOPES = ["tickets:read", "users:read"]
DEFAULT_SCOPES = " ".join(SCOPES)
REQUEST_TIMEOUT_SECONDS = 15.0


class ZendeskAdapter:
    provider_key = "zendesk"
    SCOPES = SCOPES

    def __init__(self, *, client_id: str, client_secret: str, subdomain: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._subdomain = subdomain
        self._base_url = f"https://{subdomain}.zendesk.com"

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        url = httpx.URL(
            f"{self._base_url}/oauth/authorizations/new",
            params={
                "response_type": "code",
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
                f"{self._base_url}/oauth/tokens",
                json={
                    "grant_type": "authorization_code",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                    "scope": DEFAULT_SCOPES,
                },
            )
            response.raise_for_status()
            body = response.json()
        return TokenResult(
            access_token=body["access_token"],
            refresh_token=None,
            expires_in_seconds=None,
            scopes=list(SCOPES),
        )

    async def refresh_access_token(self, *, refresh_token: str) -> TokenResult:
        raise RuntimeError(
            "Zendesk OAuth tokens issued without token rotation do not expire and cannot be "
            "refreshed; disconnect and reconnect instead"
        )

    async def test_connection(self, *, access_token: str) -> HealthResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{self._base_url}/api/v2/users/me.json",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code != 200:
            return HealthResult(
                ok=False, detail=f"Zendesk /users/me check failed (HTTP {response.status_code})"
            )
        body = response.json().get("user", {})
        user_id = body.get("id")
        return HealthResult(
            ok=True, detail="Connected", external_account_id=str(user_id) if user_id else None
        )

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult:
        """Incremental, checkpointed (spec §G2): Zendesk's cursor-based
        pagination (`links.next`/`meta.after_cursor`) is round-tripped as
        the opaque `cursor` string so each sync continues through the
        ticket list rather than always re-fetching the first page."""
        params: dict[str, str | int] = {"page[size]": 10}
        if cursor:
            params["page[after]"] = cursor
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{self._base_url}/api/v2/tickets.json",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            body = response.json()
        tickets = body.get("tickets", [])
        meta = body.get("meta", {})
        next_cursor = meta.get("after_cursor") if meta.get("has_more") else None
        return SyncResult(
            items_synced=len(tickets),
            detail="Fetched Zendesk tickets (read-only)",
            next_cursor=next_cursor,
        )

    async def revoke(self, *, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            await client.delete(
                f"{self._base_url}/api/v2/oauth/tokens/current.json",
                headers={"Authorization": f"Bearer {access_token}"},
            )
