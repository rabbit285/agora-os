"""Real Intercom OAuth2 connector adapter (spec §48's Customer Support
category).

Only instantiated when `INTERCOM_CLIENT_ID`/`INTERCOM_CLIENT_SECRET` are
configured (see `app.integrations.service.get_oauth_adapter`) — this
environment has no real Intercom developer app, so this class is never
exercised end to end here, but every method is a real HTTP call against
Intercom's documented OAuth/API endpoints, not a stub.

Known simplification (see docs/KNOWN_LIMITATIONS.md): Intercom doesn't
grant scopes via an OAuth `scope` parameter the way HubSpot/Pipedrive
do — a real Intercom app's read permissions are fixed in its Developer
Hub configuration instead, so `SCOPES` here is a descriptive label for
the permission preview shown before Connect (spec §B1), not a value
actually sent in the authorization URL. Intercom access tokens issued
this way do not expire and have no refresh flow, the same token model
Zendesk/GitHub/Slack's adapters already document.
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://app.intercom.com/oauth"
TOKEN_URL = "https://api.intercom.io/auth/eagle/token"
API_BASE_URL = "https://api.intercom.io"
SCOPES = ["contacts:read", "conversations:read"]
REQUEST_TIMEOUT_SECONDS = 15.0


class IntercomAdapter:
    provider_key = "intercom"
    SCOPES = SCOPES

    def __init__(self, *, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        url = httpx.URL(
            AUTHORIZE_URL,
            params={"client_id": self._client_id, "redirect_uri": redirect_uri, "state": state},
        )
        return str(url)

    async def exchange_code_for_tokens(self, *, code: str, redirect_uri: str) -> TokenResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                TOKEN_URL,
                json={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                },
            )
            response.raise_for_status()
            body = response.json()
        return TokenResult(
            access_token=body["token"],
            refresh_token=None,
            expires_in_seconds=None,
            scopes=list(SCOPES),
        )

    async def refresh_access_token(self, *, refresh_token: str) -> TokenResult:
        raise RuntimeError(
            "Intercom OAuth tokens do not expire and cannot be refreshed; disconnect and "
            "reconnect instead"
        )

    async def test_connection(self, *, access_token: str) -> HealthResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{API_BASE_URL}/me", headers={"Authorization": f"Bearer {access_token}"}
            )
        if response.status_code != 200:
            return HealthResult(
                ok=False, detail=f"Intercom /me check failed (HTTP {response.status_code})"
            )
        body = response.json()
        app_id = body.get("app", {}).get("id_code")
        return HealthResult(
            ok=True, detail="Connected", external_account_id=str(app_id) if app_id else None
        )

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult:
        """Incremental, checkpointed (spec §G2): Intercom's cursor-based
        `starting_after` pagination is round-tripped as the opaque
        `cursor` string so each sync continues through the contact list
        rather than always re-fetching the first page."""
        params: dict[str, str | int] = {"per_page": 10}
        if cursor:
            params["starting_after"] = cursor
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{API_BASE_URL}/contacts",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            body = response.json()
        contacts = body.get("data", [])
        next_cursor = body.get("pages", {}).get("next", {}).get("starting_after")
        return SyncResult(
            items_synced=len(contacts),
            detail="Fetched Intercom contacts (read-only)",
            next_cursor=next_cursor,
        )

    async def revoke(self, *, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            await client.post(
                f"{API_BASE_URL}/auth/uninstall",
                headers={"Authorization": f"Bearer {access_token}"},
            )
