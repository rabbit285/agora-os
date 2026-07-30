"""Real Slack OAuth2 connector adapter (spec §48's Communication category).

Only instantiated when `SLACK_CLIENT_ID`/`SLACK_CLIENT_SECRET` are
configured — this environment has no real Slack app, so this class is
never exercised end to end here, but every method is a real HTTP call
against Slack's documented OAuth v2 / Web API endpoints, not a stub.

Slack bot tokens issued by `oauth.v2.access` do not expire under Slack's
default (non-rotating) token model, so — like GitHub's classic OAuth App
tokens — there is genuinely no refresh flow to call; `refresh_access_token`
documents that rather than faking one. Scope is `channels:read` only
(spec §B1 progressive trust model, Stage 1): enough to list public
channels, nothing that can post or read message content.
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
TOKEN_URL = "https://slack.com/api/oauth.v2.access"
AUTH_TEST_URL = "https://slack.com/api/auth.test"
CONVERSATIONS_URL = "https://slack.com/api/conversations.list"
REVOKE_URL = "https://slack.com/api/auth.revoke"
SCOPES = ["channels:read"]
DEFAULT_SCOPES = ",".join(SCOPES)
REQUEST_TIMEOUT_SECONDS = 15.0


class SlackAdapter:
    provider_key = "slack"
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
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
            response.raise_for_status()
            body = response.json()
        if not body.get("ok"):
            raise ValueError(f"Slack token exchange failed: {body.get('error', 'unknown error')}")
        access_token = body.get("access_token") or body["authed_user"]["access_token"]
        return TokenResult(
            access_token=access_token,
            refresh_token=None,
            expires_in_seconds=None,
            scopes=list(SCOPES),
        )

    async def refresh_access_token(self, *, refresh_token: str) -> TokenResult:
        raise RuntimeError(
            "Slack bot tokens issued without token rotation do not expire and cannot be "
            "refreshed; disconnect and reconnect instead"
        )

    async def test_connection(self, *, access_token: str) -> HealthResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                AUTH_TEST_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            body = response.json()
        if not body.get("ok"):
            return HealthResult(ok=False, detail=f"Slack auth.test failed: {body.get('error')}")
        return HealthResult(ok=True, detail="Connected", external_account_id=body.get("team_id"))

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult:
        """Incremental, checkpointed (spec §G2): Slack's own cursor
        pagination is round-tripped so each sync continues through the
        channel list rather than always re-fetching the first page."""
        params: dict[str, str | int] = {"limit": 10, "types": "public_channel"}
        if cursor:
            params["cursor"] = cursor
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                CONVERSATIONS_URL,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            body = response.json()
        if not body.get("ok"):
            raise ValueError(f"Slack conversations.list failed: {body.get('error')}")
        channels = body.get("channels", [])
        next_cursor = body.get("response_metadata", {}).get("next_cursor") or None
        return SyncResult(
            items_synced=len(channels),
            detail="Fetched public channel list (read-only)",
            next_cursor=next_cursor,
        )

    async def revoke(self, *, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            await client.post(REVOKE_URL, headers={"Authorization": f"Bearer {access_token}"})
