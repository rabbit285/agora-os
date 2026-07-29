"""Mock OAuth adapter — used whenever a real provider isn't configured
(mirrors `app.ai.gateway.DemoAdapter`). Every result is clearly labeled as
demo data; no network call is ever made. This is also what the test suite
exercises for every provider (this environment has no real developer app
for any of the six providers), the same way AI-gateway tests run against
`DemoAdapter` rather than a real provider.

Takes `provider_key` so a mocked Google connection is distinguishable from
a mocked Slack connection in logs/UI even before real credentials exist —
`provider_key` is never used to fabricate a "real" result, only to label
demo output honestly (spec §82).
"""

from __future__ import annotations

import secrets

from app.integrations.adapters.base import HealthResult, SyncResult, TokenResult


class MockOAuthAdapter:
    def __init__(self, *, provider_key: str = "mock") -> None:
        self.provider_key = provider_key
        self.SCOPES = ["mock.read"]

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        return (
            f"http://mock-oauth.invalid/authorize?provider={self.provider_key}"
            f"&state={state}&redirect_uri={redirect_uri}"
        )

    async def exchange_code_for_tokens(self, *, code: str, redirect_uri: str) -> TokenResult:
        return TokenResult(
            access_token=f"mock-access-{secrets.token_hex(8)}",
            refresh_token=f"mock-refresh-{secrets.token_hex(8)}",
            expires_in_seconds=3600,
            scopes=list(self.SCOPES),
        )

    async def refresh_access_token(self, *, refresh_token: str) -> TokenResult:
        return TokenResult(
            access_token=f"mock-access-{secrets.token_hex(8)}",
            refresh_token=refresh_token,
            expires_in_seconds=3600,
            scopes=list(self.SCOPES),
        )

    async def test_connection(self, *, access_token: str) -> HealthResult:
        return HealthResult(
            ok=True,
            detail=(
                f"Mock {self.provider_key} connection healthy "
                "(demo mode — no real provider configured)"
            ),
            external_account_id=f"mock-{self.provider_key}-account-0001",
        )

    async def sync(self, *, access_token: str) -> SyncResult:
        return SyncResult(
            items_synced=3,
            detail=f"Demo {self.provider_key} sync — 3 sample records (no real provider configured)",
        )

    async def revoke(self, *, access_token: str) -> None:
        return None
