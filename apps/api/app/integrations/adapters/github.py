"""Real GitHub OAuth2 connector adapter (spec §48's Engineering category).

Only instantiated when `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` are
configured — this environment has no real GitHub OAuth App, so this class
is never exercised end to end here, but every method is a real HTTP call
against GitHub's documented OAuth/REST endpoints, not a stub.

Classic GitHub OAuth App tokens (as opposed to a GitHub App's
installation tokens) do not expire and have no refresh token, so
`refresh_access_token` is genuinely unsupported here, not an oversight —
`app.integrations.service.refresh_connection_token` never reaches it
anyway, since it first checks for a stored refresh token and GitHub's
`exchange_code_for_tokens` never sets one.

Scope is `read:user` only — identity, not repository access — so `sync`
reads the authenticated user's already-public repositories (data anyone
can already read), never anything requiring a write or private-data
scope (spec §B1 progressive trust model, Stage 1).
"""

from __future__ import annotations

import httpx

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
PUBLIC_REPOS_URL = "https://api.github.com/users/{login}/repos"
REVOKE_URL = "https://api.github.com/applications/{client_id}/grant"
SCOPES = ["read:user"]
DEFAULT_SCOPES = " ".join(SCOPES)
REQUEST_TIMEOUT_SECONDS = 15.0
API_VERSION_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class GitHubAdapter:
    provider_key = "github"
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
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            body = response.json()
        if "error" in body:
            raise ValueError(
                f"GitHub token exchange failed: {body.get('error_description', body['error'])}"
            )
        return TokenResult(
            access_token=body["access_token"],
            refresh_token=None,
            expires_in_seconds=None,
            scopes=list(SCOPES),
        )

    async def refresh_access_token(self, *, refresh_token: str) -> TokenResult:
        raise RuntimeError(
            "GitHub classic OAuth App tokens do not expire and cannot be refreshed; "
            "disconnect and reconnect instead"
        )

    async def test_connection(self, *, access_token: str) -> HealthResult:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                USER_URL,
                headers={"Authorization": f"Bearer {access_token}", **API_VERSION_HEADERS},
            )
        if response.status_code != 200:
            return HealthResult(
                ok=False, detail=f"GitHub /user check failed (HTTP {response.status_code})"
            )
        body = response.json()
        return HealthResult(
            ok=True,
            detail="Connected",
            external_account_id=str(body.get("id")) if body.get("id") else body.get("login"),
        )

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult:
        """Incremental, checkpointed (spec §G2): GitHub's REST pagination
        is page-number based (`?page=N`); the next page number is
        round-tripped as the opaque `cursor` string, and derived from
        whether the response's `Link` header advertises a `rel="next"`
        page rather than assumed."""
        page = int(cursor) if cursor else 1
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            me = await client.get(
                USER_URL,
                headers={"Authorization": f"Bearer {access_token}", **API_VERSION_HEADERS},
            )
            me.raise_for_status()
            login = me.json()["login"]
            response = await client.get(
                PUBLIC_REPOS_URL.format(login=login),
                params={"per_page": 10, "sort": "updated", "page": page},
                headers=API_VERSION_HEADERS,
            )
            response.raise_for_status()
            repos = response.json()
        next_cursor = str(page + 1) if 'rel="next"' in response.headers.get("Link", "") else None
        return SyncResult(
            items_synced=len(repos),
            detail=f"Fetched {login}'s public repositories (read-only)",
            next_cursor=next_cursor,
        )

    async def revoke(self, *, access_token: str) -> None:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            await client.request(
                "DELETE",
                REVOKE_URL.format(client_id=self._client_id),
                auth=(self._client_id, self._client_secret),
                json={"access_token": access_token},
                headers=API_VERSION_HEADERS,
            )
