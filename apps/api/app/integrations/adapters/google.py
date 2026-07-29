"""Real Google OAuth2 connector adapter (spec §48's Documents/Communication
categories — Calendar chosen as the representative read-only capability).

Only instantiated when `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are
configured (see `app.integrations.adapters.get_oauth_adapter`) — this
environment has no real Google Cloud OAuth client, so this class is never
exercised end to end here, but every method is a real HTTP call against
Google's documented OAuth2/Calendar endpoints, not a stub. Read-only
Calendar scope only (spec §B1 progressive trust model, Stage 1).

`access_type=offline` + `prompt=consent` on the authorize URL are what make
Google actually issue a refresh token — Google otherwise omits it on
repeat authorizations for the same user/client pair.
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPES = ["openid", "email", "https://www.googleapis.com/auth/calendar.readonly"]
DEFAULT_SCOPES = " ".join(SCOPES)
REQUEST_TIMEOUT_SECONDS = 15.0


class GoogleAdapter:
    provider_key = "google"
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
                "scope": DEFAULT_SCOPES,
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
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
                },
            )
            response.raise_for_status()
            body = response.json()
        return TokenResult(
            access_token=body["access_token"],
            # Google does not re-issue a refresh token on refresh — keep the
            # caller's existing one.
            refresh_token=body.get("refresh_token", refresh_token),
            expires_in_seconds=body.get("expires_in"),
            scopes=list(SCOPES),
        )

    async def test_connection(self, *, access_token: str) -> HealthResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
        if response.status_code != 200:
            return HealthResult(
                ok=False, detail=f"Google userinfo check failed (HTTP {response.status_code})"
            )
        body = response.json()
        return HealthResult(ok=True, detail="Connected", external_account_id=body.get("sub"))

    async def sync(self, *, access_token: str) -> SyncResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                CALENDAR_EVENTS_URL,
                params={"maxResults": 10, "singleEvents": "true", "orderBy": "startTime"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            body = response.json()
        items = body.get("items", [])
        return SyncResult(
            items_synced=len(items), detail="Fetched upcoming primary-calendar events (read-only)"
        )

    async def revoke(self, *, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            await client.post(REVOKE_URL, params={"token": access_token})
