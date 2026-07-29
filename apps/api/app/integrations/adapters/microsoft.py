"""Real Microsoft OAuth2 connector adapter (spec §48's Communication/
Documents categories — Microsoft Graph, Calendar chosen as the
representative read-only capability, mirroring the Google adapter's choice).

Only instantiated when `MICROSOFT_CLIENT_ID`/`MICROSOFT_CLIENT_SECRET` are
configured — this environment has no real Azure AD app registration, so
this class is never exercised end to end here, but every method is a real
HTTP call against Microsoft's documented identity platform (v2.0) / Graph
endpoints, not a stub. Uses the multi-tenant "common" authority so both
work and personal Microsoft accounts can authorize, matching how a
platform integration (as opposed to a single-tenant internal tool) would
be registered. Read-only scopes only (spec §B1 progressive trust model,
Stage 1).
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
ME_URL = "https://graph.microsoft.com/v1.0/me"
EVENTS_URL = "https://graph.microsoft.com/v1.0/me/events"
SCOPES = ["offline_access", "User.Read", "Calendars.Read"]
DEFAULT_SCOPES = " ".join(SCOPES)
REQUEST_TIMEOUT_SECONDS = 15.0


class MicrosoftAdapter:
    provider_key = "microsoft"
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
                "response_type": "code",
                "response_mode": "query",
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
                    "scope": DEFAULT_SCOPES,
                },
            )
            response.raise_for_status()
            body = response.json()
        return TokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_in_seconds=body.get("expires_in"),
            scopes=list(SCOPES),
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
                    "scope": DEFAULT_SCOPES,
                },
            )
            response.raise_for_status()
            body = response.json()
        return TokenResult(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", refresh_token),
            expires_in_seconds=body.get("expires_in"),
            scopes=list(SCOPES),
        )

    async def test_connection(self, *, access_token: str) -> HealthResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(ME_URL, headers={"Authorization": f"Bearer {access_token}"})
        if response.status_code != 200:
            return HealthResult(
                ok=False, detail=f"Microsoft Graph /me check failed (HTTP {response.status_code})"
            )
        body = response.json()
        return HealthResult(ok=True, detail="Connected", external_account_id=body.get("id"))

    async def sync(self, *, access_token: str) -> SyncResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                EVENTS_URL,
                params={"$top": 10},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            body = response.json()
        items = body.get("value", [])
        return SyncResult(
            items_synced=len(items), detail="Fetched upcoming Outlook calendar events (read-only)"
        )

    async def revoke(self, *, access_token: str) -> None:
        # Microsoft Graph has no direct access-token revocation endpoint for
        # individual tokens (unlike full sign-out, which isn't applicable to
        # a server-to-server integration token); clearing our own stored
        # copy (done by the caller) is the practical equivalent, same as
        # HubSpot's revoke.
        return None
