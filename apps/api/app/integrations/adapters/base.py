"""Provider-neutral OAuth2 connector adapter interface (spec §49's
Connector Contract). Mirrors `app.ai.gateway`'s `ModelAdapter`/`DemoAdapter`
pattern: a `Protocol` every real provider implements, plus a Mock adapter
(`app.integrations.adapters.mock.MockOAuthAdapter`) used whenever no real
provider credentials are configured — never presented as a live connection
to end users (the provider catalog endpoint reports `configured: bool`
honestly; see `app.integrations.service`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class TokenResult:
    access_token: str
    refresh_token: str | None
    expires_in_seconds: int | None
    scopes: list[str] = field(default_factory=list)


@dataclass
class HealthResult:
    ok: bool
    detail: str
    external_account_id: str | None = None


@dataclass
class SyncResult:
    items_synced: int
    detail: str
    # spec §G2 "incremental cursors"/"checkpointing": the provider's own
    # pagination cursor (HubSpot's `after`, Slack's `next_cursor`,
    # Microsoft's `@odata.nextLink` skip token, Google's `nextPageToken`,
    # GitHub's next page number) to resume from on the next sync rather
    # than always re-fetching the same first page. `None` means either
    # the provider reported no further pages (a full pass just
    # completed — the next sync starts over from the beginning) or this
    # adapter's endpoint has no meaningful pagination (Salesforce's
    # single-item identity check).
    next_cursor: str | None = None


class OAuthConnectorAdapter(Protocol):
    provider_key: str
    # The scopes this provider requests, requested-form (space/comma exact
    # syntax is provider-specific — see each adapter's authorization_url).
    # Class-level so the provider catalog can show a permission preview
    # without constructing an adapter (real adapters require client
    # credentials to construct; this list is needed even when unconfigured).
    SCOPES: list[str]

    def authorization_url(self, *, state: str, redirect_uri: str) -> str: ...

    async def exchange_code_for_tokens(self, *, code: str, redirect_uri: str) -> TokenResult: ...

    async def refresh_access_token(self, *, refresh_token: str) -> TokenResult: ...

    async def test_connection(self, *, access_token: str) -> HealthResult: ...

    async def sync(self, *, access_token: str, cursor: str | None = None) -> SyncResult: ...

    async def revoke(self, *, access_token: str) -> None: ...
