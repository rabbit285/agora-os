"""Real Apollo.io OAuth2 connector adapter — the customer-connected
credential source for the Sales Lead Finder (see
docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md).

Distinct from `app.sales.providers.apollo.ApolloDataProvider`, which is the
*capability* adapter (company/people search, enrichment). This class owns
only the OAuth token lifecycle; the Sales provider consumes the token it
stores. Both are keyed "apollo" but implement different Protocols in
different packages — see the architecture doc §1.

Only instantiated when `APOLLO_OAUTH_CLIENT_ID`/`APOLLO_OAUTH_CLIENT_SECRET`
are configured (`app.integrations.adapters.get_oauth_adapter`); until Apollo
approves the registered OAuth application, the mock adapter is used instead
and nothing in the product claims Apollo is approved or connected.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.config import settings
from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

# Least-privilege: exactly the scopes this build's implemented capabilities
# need (architecture §4). No write scopes — Veyntra never creates
# Apollo sequences, contacts, accounts, or tasks.
SCOPES = [
    "read_user_profile",
    "mixed_companies_search",
    "mixed_people_api_search",
    "organizations_enrich",
    "people_match",
    "api_usage_stats_read",
]
REQUEST_TIMEOUT_SECONDS = 20.0


class ApolloOAuthError(Exception):
    """Token exchange/refresh failure, carrying Apollo's own OAuth error
    code (e.g. "invalid_grant") when it supplies one, so callers can
    distinguish "reconnect required" from a transient failure without
    parsing a message string. Never carries a raw response body."""

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class ApolloOAuthAdapter:
    provider_key = "apollo"
    SCOPES = SCOPES

    def __init__(self, *, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        # Apollo's authorize route is a *fragment* route
        # ("https://app.apollo.io/#/oauth/authorize"), so the query string
        # goes after the fragment for its SPA router to parse — unlike
        # every other adapter here, which can hand params to httpx.URL.
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(SCOPES),
                "state": state,
            }
        )
        base = settings.apollo_oauth_authorize_url
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}{query}"

    async def _token_request(self, data: dict[str, str]) -> TokenResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.post(settings.apollo_oauth_token_url, data=data)
            except httpx.RequestError as exc:
                raise ApolloOAuthError(f"Apollo token endpoint unreachable: {exc}") from exc

        if response.status_code != 200:
            # Apollo's OAuth errors follow the RFC 6749 shape
            # ({"error": "invalid_grant", ...}). Only the machine-readable
            # code is propagated — never the raw body.
            error_code: str | None = None
            try:
                error_code = response.json().get("error")
            except ValueError:
                error_code = None
            raise ApolloOAuthError(
                f"Apollo rejected the token request (HTTP {response.status_code})",
                error_code=error_code,
            )

        body = response.json()
        access_token = body.get("access_token")
        if not access_token:
            raise ApolloOAuthError("Apollo token response contained no access token")

        # Apollo returns granted scopes as a space-delimited string; fall
        # back to the requested set only when it omits the field entirely,
        # so a downgraded grant is never reported as if it were full.
        granted = body.get("scope")
        scopes = granted.split() if isinstance(granted, str) and granted else list(SCOPES)

        return TokenResult(
            access_token=access_token,
            refresh_token=body.get("refresh_token"),
            expires_in_seconds=body.get("expires_in"),
            scopes=scopes,
        )

    async def exchange_code_for_tokens(self, *, code: str, redirect_uri: str) -> TokenResult:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": redirect_uri,
            }
        )

    async def refresh_access_token(self, *, refresh_token: str) -> TokenResult:
        result = await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        )
        # Apollo may or may not rotate the refresh token; keep the existing
        # one when it doesn't, so the connection stays refreshable.
        if result.refresh_token is None:
            result.refresh_token = refresh_token
        return result

    async def test_connection(self, *, access_token: str) -> HealthResult:
        """Identifies the Apollo user who authorized this connection.
        Requests act as that user, so the UI shows it explicitly
        (architecture §9)."""
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(
                    f"{settings.apollo_api_base_url}/auth/health",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            except httpx.RequestError as exc:
                return HealthResult(ok=False, detail=f"Apollo unreachable: {exc}")

        if response.status_code != 200:
            return HealthResult(
                ok=False, detail=f"Apollo health check failed (HTTP {response.status_code})"
            )
        body = response.json()
        if not body.get("is_logged_in", body.get("healthy", False)):
            return HealthResult(ok=False, detail="Apollo did not recognize the access token")
        return HealthResult(ok=True, detail="Connected")

    async def fetch_user_profile(self, *, access_token: str) -> dict[str, str | None]:
        """The connected Apollo user's non-sensitive identity, for display
        on the connection card. Returns only keys Apollo actually supplied —
        a workspace/team identifier is never inferred when Apollo omits it
        (architecture §9)."""
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(
                    f"{settings.apollo_api_base_url}/users/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            except httpx.RequestError:
                return {}
        if response.status_code != 200:
            return {}
        body = response.json()
        user = body.get("user") if isinstance(body.get("user"), dict) else body
        return {
            "provider_user_id": str(user.get("id")) if user.get("id") else None,
            "provider_user_email": user.get("email"),
            "provider_workspace_id": (
                str(user.get("organization_id")) if user.get("organization_id") else None
            ),
            "provider_workspace_name": (user.get("organization") or {}).get("name")
            if isinstance(user.get("organization"), dict)
            else None,
        }

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult:
        """Apollo is a search/enrichment provider, not a CRM object source —
        there is no periodic object sync to run. Honest no-op rather than a
        fabricated record count; Lead Finder search/enrichment is the real
        data path (see app.sales.providers.apollo)."""
        return SyncResult(
            items_synced=0,
            detail=(
                "Apollo has no background sync — company/people data is fetched on demand "
                "through Lead Finder search and enrichment."
            ),
            next_cursor=None,
        )

    async def revoke(self, *, access_token: str) -> None:
        """Apollo publishes no token-revocation endpoint. Clearing the
        stored tokens (done by the caller in `disconnect_connection`) is the
        real, disclosed extent of disconnection — this build does not invent
        a revocation URL. See docs/KNOWN_LIMITATIONS.md."""
        return None
