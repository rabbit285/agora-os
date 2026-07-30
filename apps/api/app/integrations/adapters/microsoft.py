"""Real Microsoft OAuth2 connector adapter (spec §48's Communication
category via Calendar, Email category via Outlook Mail — one Microsoft
connection legitimately covers both, the same way the Google adapter
combines Calendar/Gmail/Drive under a single connection).

Only instantiated when `MICROSOFT_CLIENT_ID`/`MICROSOFT_CLIENT_SECRET` are
configured — this environment has no real Azure AD app registration, so
this class is never exercised end to end here, but every method is a real
HTTP call against Microsoft's documented identity platform (v2.0) / Graph
endpoints, not a stub. Uses the multi-tenant "common" authority so both
work and personal Microsoft accounts can authorize, matching how a
platform integration (as opposed to a single-tenant internal tool) would
be registered. Read-only scopes only (spec §B1 progressive trust model,
Stage 1).

Known simplification (see docs/KNOWN_LIMITATIONS.md): spec §G2 incremental
cursor/checkpointing only round-trips the Calendar events list's
`@odata.nextLink` (the original resource this adapter supported) — Outlook
Mail was added later as a broader read-only footprint on the same
connection and always fetches its most recent first page, the same
disclosed simplification the Google adapter makes for Gmail/Drive.
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
ME_URL = "https://graph.microsoft.com/v1.0/me"
EVENTS_URL = "https://graph.microsoft.com/v1.0/me/events"
MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/messages"
SCOPES = ["offline_access", "User.Read", "Calendars.Read", "Mail.Read"]
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

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult:
        """Incremental, checkpointed (spec §G2) for Calendar only:
        Microsoft Graph's own `@odata.nextLink` is a fully-formed next-page
        URL, so it is used directly as the request URL when a cursor is
        present, and round-tripped back out as the opaque `cursor` string.
        Outlook Mail (see module docstring) always fetches its latest
        first page."""
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            if cursor:
                events_response = await client.get(cursor, headers=headers)
            else:
                events_response = await client.get(
                    EVENTS_URL, params={"$top": 10}, headers=headers
                )
            events_response.raise_for_status()
            events_body = events_response.json()

            messages_response = await client.get(
                MESSAGES_URL, params={"$top": 10}, headers=headers
            )
            messages_response.raise_for_status()
            messages_body = messages_response.json()

        events = events_body.get("value", [])
        messages = messages_body.get("value", [])
        next_cursor = events_body.get("@odata.nextLink")
        return SyncResult(
            items_synced=len(events) + len(messages),
            detail=(
                f"Fetched {len(events)} upcoming Outlook calendar events, {len(messages)} recent "
                "Outlook Mail messages (both read-only)"
            ),
            next_cursor=next_cursor,
        )

    async def revoke(self, *, access_token: str) -> None:
        # Microsoft Graph has no direct access-token revocation endpoint for
        # individual tokens (unlike full sign-out, which isn't applicable to
        # a server-to-server integration token); clearing our own stored
        # copy (done by the caller) is the practical equivalent, same as
        # HubSpot's revoke.
        return None
