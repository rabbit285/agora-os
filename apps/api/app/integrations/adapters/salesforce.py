"""Real Salesforce OAuth2 connector adapter (spec §48's CRM category, a
second CRM provider alongside HubSpot).

Only instantiated when `SALESFORCE_CLIENT_ID`/`SALESFORCE_CLIENT_SECRET`
are configured — this environment has no real Salesforce Connected App, so
this class is never exercised end to end here, but every method is a real
HTTP call against Salesforce's documented OAuth2 endpoints, not a stub.

Known simplification (see `docs/KNOWN_LIMITATIONS.md`): a real Salesforce
integration must call the org's own instance-specific domain (e.g.
`https://mycompany.my.salesforce.com`, returned as `instance_url` in the
token response) for anything beyond identity/revoke — those two endpoints
are documented to also work at the generic `login.salesforce.com` domain
regardless of the org's actual instance, which is what `test_connection`,
`sync`, and `revoke` use here rather than threading a per-connection
instance URL through the generic `OAuthConnectorAdapter` Protocol (every
other provider's methods are instance-independent, so this would be a
Salesforce-only parameter). A production Salesforce connector should
persist `instance_url` and use it for any real data API call.
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://login.salesforce.com/services/oauth2/authorize"
TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"
USERINFO_URL = "https://login.salesforce.com/services/oauth2/userinfo"
REVOKE_URL = "https://login.salesforce.com/services/oauth2/revoke"
SCOPES = ["api", "refresh_token"]
DEFAULT_SCOPES = " ".join(SCOPES)
REQUEST_TIMEOUT_SECONDS = 15.0


class SalesforceAdapter:
    provider_key = "salesforce"
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
            # Salesforce access tokens don't carry a fixed lifetime in the
            # token response; sessions are typically valid ~2 hours by org
            # policy. None here means `ensure_fresh_access_token` never
            # proactively refreshes — a 401 from a stale token would need to
            # trigger a reconnect, same as GitHub/Slack's non-expiring model.
            expires_in_seconds=None,
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
            refresh_token=body.get("refresh_token", refresh_token),
            expires_in_seconds=None,
            scopes=list(SCOPES),
        )

    async def test_connection(self, *, access_token: str) -> HealthResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
        if response.status_code != 200:
            return HealthResult(
                ok=False, detail=f"Salesforce userinfo check failed (HTTP {response.status_code})"
            )
        body = response.json()
        return HealthResult(
            ok=True, detail="Connected", external_account_id=body.get("user_id") or body.get("sub")
        )

    async def sync(self, *, access_token: str) -> SyncResult:
        # See the module docstring's "Known simplification": without a
        # persisted instance_url, the only endpoint this adapter can call
        # honestly (real data, real HTTP call) via the generic login domain
        # is the same identity endpoint health uses.
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
        return SyncResult(
            items_synced=1,
            detail=(
                "Re-verified the connected Salesforce identity (read-only) — a full data sync "
                "needs the org's instance-specific API domain, not yet wired up"
            ),
        )

    async def revoke(self, *, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            await client.post(REVOKE_URL, params={"token": access_token})
