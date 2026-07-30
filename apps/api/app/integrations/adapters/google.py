"""Real Google OAuth2 connector adapter (spec §48's Communication category
via Calendar, Email category via Gmail, Documents category via Drive — one
Google connection legitimately covers all three, the same way a real
Google Workspace app requests one combined scope set rather than three
separate connections).

Only instantiated when `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are
configured (see `app.integrations.adapters.get_oauth_adapter`) — this
environment has no real Google Cloud OAuth client, so this class is never
exercised end to end here, but every method is a real HTTP call against
Google's documented OAuth2/Calendar/Gmail/Drive endpoints, not a stub.
Read-only scopes only (spec §B1 progressive trust model, Stage 1).

`access_type=offline` + `prompt=consent` on the authorize URL are what make
Google actually issue a refresh token — Google otherwise omits it on
repeat authorizations for the same user/client pair.

Known simplification (see docs/KNOWN_LIMITATIONS.md): spec §G2 incremental
cursor/checkpointing only round-trips Calendar's `nextPageToken` (the
original resource this adapter supported) — Gmail and Drive were added
later as a broader read-only footprint on the same connection and always
fetch their most recent first page rather than each carrying their own
checkpoint, which would need `IntegrationConnection.sync_cursor` to hold
three independent cursor values instead of one opaque string.
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
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

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult:
        """Incremental, checkpointed (spec §G2) for Calendar only: Google
        Calendar's own `nextPageToken` is round-tripped as the opaque
        `cursor` string so each sync continues through the event list
        instead of always re-fetching the same first page. Gmail and
        Drive (see module docstring) always fetch their latest first page."""
        params: dict[str, str | int] = {
            "maxResults": 10,
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        if cursor:
            params["pageToken"] = cursor
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            calendar_response = await client.get(
                CALENDAR_EVENTS_URL, params=params, headers=headers
            )
            calendar_response.raise_for_status()
            calendar_body = calendar_response.json()

            gmail_response = await client.get(
                GMAIL_MESSAGES_URL, params={"maxResults": 10}, headers=headers
            )
            gmail_response.raise_for_status()
            gmail_body = gmail_response.json()

            drive_response = await client.get(
                DRIVE_FILES_URL,
                params={"pageSize": 10, "fields": "files(id,name)"},
                headers=headers,
            )
            drive_response.raise_for_status()
            drive_body = drive_response.json()

        events = calendar_body.get("items", [])
        messages = gmail_body.get("messages", [])
        files = drive_body.get("files", [])
        next_cursor = calendar_body.get("nextPageToken")
        return SyncResult(
            items_synced=len(events) + len(messages) + len(files),
            detail=(
                f"Fetched {len(events)} upcoming calendar events, {len(messages)} recent Gmail "
                f"messages, {len(files)} recent Drive files (all read-only)"
            ),
            next_cursor=next_cursor,
        )

    async def revoke(self, *, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            await client.post(REVOKE_URL, params={"token": access_token})
