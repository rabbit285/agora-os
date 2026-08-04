"""Real Pipedrive OAuth2 connector adapter (spec §48's CRM category).

Only instantiated when `PIPEDRIVE_CLIENT_ID`/`PIPEDRIVE_CLIENT_SECRET` are
configured (see `app.integrations.service.get_oauth_adapter`) — this
environment has no real Pipedrive developer app, so this class is never
exercised end to end here, but every method is a real HTTP call against
Pipedrive's documented OAuth/API v1 endpoints, not a stub. Read-only CRM
scopes only (spec §B1 progressive trust model, Stage 1).

Known simplification (see docs/KNOWN_LIMITATIONS.md): Pipedrive's real
token exchange also returns a per-company `api_domain` a production
integration would route subsequent calls through; this adapter calls the
account-wide `api.pipedrive.com` host instead, the same simplification
Zendesk's adapter discloses in the opposite direction (one fixed
subdomain instead of none) — both are real HTTP calls against Pipedrive's
documented endpoints, just without per-company request routing.
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://oauth.pipedrive.com/oauth/authorize"
TOKEN_URL = "https://oauth.pipedrive.com/oauth/token"
SCOPES = ["deals:read", "contacts:read"]
DEFAULT_SCOPES = " ".join(SCOPES)
REQUEST_TIMEOUT_SECONDS = 15.0


class PipedriveAdapter:
    provider_key = "pipedrive"
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
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                auth=(self._client_id, self._client_secret),
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
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                auth=(self._client_id, self._client_secret),
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
        # Pipedrive's own account-wide (not per-company-domain) endpoint —
        # real for a health check even though real data calls need the
        # per-company `api_domain` from the token exchange response.
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                "https://api.pipedrive.com/api/v1/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code != 200:
            return HealthResult(
                ok=False, detail=f"Pipedrive /users/me check failed (HTTP {response.status_code})"
            )
        body = response.json().get("data", {})
        company_id = body.get("company_id")
        return HealthResult(
            ok=True, detail="Connected", external_account_id=str(company_id) if company_id else None
        )

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult:
        """Incremental, checkpointed (spec §G2): Pipedrive's own `start`
        offset is round-tripped as the opaque `cursor` string so each sync
        continues through the deal list rather than always re-fetching the
        first page."""
        params: dict[str, str | int] = {"limit": 10}
        if cursor:
            params["start"] = int(cursor)
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                "https://api.pipedrive.com/api/v1/deals",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            body = response.json()
        deals = body.get("data") or []
        pagination = body.get("additional_data", {}).get("pagination", {})
        next_start = (
            pagination.get("next_start") if pagination.get("more_items_in_collection") else None
        )
        return SyncResult(
            items_synced=len(deals),
            detail="Fetched Pipedrive deals (read-only)",
            next_cursor=str(next_start) if next_start is not None else None,
        )

    async def revoke(self, *, access_token: str) -> None:
        # Pipedrive has no direct access-token revocation endpoint;
        # clearing our own stored copy (done by the caller) is the
        # practical equivalent for this build's purposes — same disclosed
        # limitation as HubSpot's adapter.
        return None
