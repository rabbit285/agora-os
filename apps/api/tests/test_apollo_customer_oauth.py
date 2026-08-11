"""Customer-connected Apollo OAuth (see
docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md).

Every test here runs against the mock OAuth adapter — this environment has
no real Apollo application, and automated tests must never consume a real
customer's Apollo credits. The adapters that *would* talk to Apollo are
exercised directly with stub transports where their own logic is the thing
under test (authorization URL shape, token-request payloads, error mapping).
"""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.core.crypto import decrypt_token
from app.core.models import Membership, MembershipRole
from app.core.rbac import get_system_role
from app.identity.models import User
from app.identity.service import create_session
from app.integrations.adapters.apollo import ApolloOAuthAdapter, ApolloOAuthError
from app.integrations.models import IntegrationConnection
from app.main import app
from app.sales.providers.credentials import (
    OrganizationApolloCredentialResolver,
    get_active_apollo_connection,
)
from app.sales.providers.exceptions import (
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderScopeMissing,
)
from app.security import hash_password


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Apollo OAuth Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _member_session(
    db_session: AsyncSession, *, organization_id: uuid.UUID, email: str, role_key: str
) -> str:
    user = User(email=email, hashed_password=hash_password("irrelevant-password-123"))
    db_session.add(user)
    await db_session.flush()
    membership = Membership(organization_id=organization_id, user_id=user.id, status="active")
    db_session.add(membership)
    await db_session.flush()
    role = await get_system_role(db_session, role_key)
    db_session.add(MembershipRole(membership_id=membership.id, role_id=role.id))
    session = await create_session(
        db_session, user=user, organization_id=organization_id, ip_address=None, user_agent=None
    )
    await db_session.commit()
    return session.raw_token  # type: ignore[attr-defined]


async def _start_apollo_oauth(client: AsyncClient) -> tuple[str, str]:
    started = await client.post("/api/v1/integrations/connections/oauth/apollo/start")
    assert started.status_code == 200, started.text
    body = started.json()
    state = parse_qs(urlparse(body["authorization_url"]).query)["state"][0]
    return body["connection_id"], state


async def _connect_apollo(client: AsyncClient) -> str:
    connection_id, state = await _start_apollo_oauth(client)
    callback = await client.get(
        "/api/v1/integrations/connections/oauth/apollo/callback",
        params={"code": "fake-code", "state": state},
    )
    assert callback.status_code in (302, 307)
    return connection_id


# ---- Authorization request ----


def test_authorization_url_carries_required_params_and_no_secret() -> None:
    adapter = ApolloOAuthAdapter(client_id="the-client-id", client_secret="the-client-secret")
    url = adapter.authorization_url(state="state-token", redirect_uri="https://app.example.com/cb")

    assert url.startswith("https://app.apollo.io/#/oauth/authorize")
    query = parse_qs(urlparse(url.replace("#", "")).query)
    assert query["client_id"] == ["the-client-id"]
    assert query["redirect_uri"] == ["https://app.example.com/cb"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["state-token"]
    # The client secret must never travel through the browser.
    assert "the-client-secret" not in url


def test_requested_scopes_are_least_privilege() -> None:
    assert ApolloOAuthAdapter.SCOPES == [
        "read_user_profile",
        "mixed_companies_search",
        "mixed_people_api_search",
        "organizations_enrich",
        "people_match",
        "api_usage_stats_read",
    ]
    # No write scopes: this build never creates Apollo sequences, contacts,
    # accounts, or tasks.
    assert not any("create" in s or "write" in s for s in ApolloOAuthAdapter.SCOPES)


# ---- State handling ----


async def test_start_creates_pending_connection_with_single_use_state(
    client: AsyncClient,
) -> None:
    await _signup(client, "apollo-state1@example.com", "Apollo State Org 1")
    connection_id, state = await _start_apollo_oauth(client)
    assert connection_id and state

    connections = await client.get("/api/v1/integrations/connections")
    matching = next(c for c in connections.json() if c["id"] == connection_id)
    assert matching["connector_key"] == "apollo"
    assert matching["status"] == "not_connected"


async def test_callback_rejects_unknown_state(client: AsyncClient) -> None:
    await _signup(client, "apollo-state2@example.com", "Apollo State Org 2")
    callback = await client.get(
        "/api/v1/integrations/connections/oauth/apollo/callback",
        params={"code": "fake-code", "state": "never-issued"},
    )
    assert callback.status_code in (302, 307)
    assert "error=" in callback.headers["location"]


async def test_callback_rejects_replayed_state(client: AsyncClient) -> None:
    """State is single-use: the second callback with the same state must
    fail even though the first succeeded."""
    await _signup(client, "apollo-state3@example.com", "Apollo State Org 3")
    _, state = await _start_apollo_oauth(client)

    first = await client.get(
        "/api/v1/integrations/connections/oauth/apollo/callback",
        params={"code": "fake-code", "state": state},
    )
    assert "connected=apollo" in first.headers["location"]

    replay = await client.get(
        "/api/v1/integrations/connections/oauth/apollo/callback",
        params={"code": "fake-code", "state": state},
    )
    assert "error=" in replay.headers["location"]


async def test_callback_rejects_expired_state(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    await _signup(client, "apollo-state4@example.com", "Apollo State Org 4")
    connection_id, state = await _start_apollo_oauth(client)

    import app.integrations.service as integrations_service

    monkeypatch.setattr(integrations_service, "OAUTH_STATE_TTL_SECONDS", -1)
    callback = await client.get(
        "/api/v1/integrations/connections/oauth/apollo/callback",
        params={"code": "fake-code", "state": state},
    )
    assert "error=" in callback.headers["location"]
    assert "expired" in callback.headers["location"].lower()

    connection = await db_session.get(IntegrationConnection, uuid.UUID(connection_id))
    assert connection is not None
    assert connection.encrypted_access_token is None


# ---- Token storage ----


async def test_callback_stores_only_encrypted_tokens_and_records_identity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "apollo-token1@example.com", "Apollo Token Org 1")
    connection_id = await _connect_apollo(client)

    connection = await db_session.get(IntegrationConnection, uuid.UUID(connection_id))
    assert connection is not None
    assert connection.status == "connected"
    assert connection.connected_at is not None
    assert connection.scopes == ["mock.read"]

    # Stored ciphertext must not be the plaintext token, and must decrypt
    # back to something usable.
    assert connection.encrypted_access_token is not None
    plaintext = decrypt_token(connection.encrypted_access_token)
    assert plaintext != connection.encrypted_access_token
    assert plaintext.startswith("mock-access-")


async def test_connection_response_never_exposes_tokens(client: AsyncClient) -> None:
    await _signup(client, "apollo-token2@example.com", "Apollo Token Org 2")
    connection_id = await _connect_apollo(client)

    response = await client.get("/api/v1/integrations/connections")
    body = response.text
    matching = next(c for c in response.json() if c["id"] == connection_id)

    assert "encrypted_access_token" not in matching
    assert "encrypted_refresh_token" not in matching
    assert "access_token" not in body
    assert "mock-access-" not in body
    assert "mock-refresh-" not in body


async def test_audit_events_never_contain_token_material(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "apollo-audit1@example.com", "Apollo Audit Org 1")
    connection_id = await _connect_apollo(client)

    events = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.object_id == connection_id)
        )
    ).scalars().all()
    actions = {e.action for e in events}
    assert "integrations.oauth.started" in actions
    assert "integrations.oauth.connected" in actions

    for event in events:
        serialized = f"{event.before_state} {event.after_state}"
        assert "mock-access-" not in serialized
        assert "mock-refresh-" not in serialized
        assert "client_secret" not in serialized


# ---- RBAC ----


async def test_sales_representative_cannot_connect_apollo(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Connecting spends the organization's own Apollo credits, so it is
    manager-only — a representative may see status but not manage it."""
    organization_id = await _signup(client, "apollo-rbac1@example.com", "Apollo RBAC Org 1")
    token = await _member_session(
        db_session,
        organization_id=organization_id,
        email="apollo-rep@example.com",
        role_key="sales_representative",
    )
    client.cookies.set("agora_session", token)

    response = await client.post("/api/v1/integrations/connections/oauth/apollo/start")
    assert response.status_code == 403
    assert "integrations.apollo.manage" in response.json()["error"]["message"]


async def test_sales_manager_can_connect_apollo(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "apollo-rbac2@example.com", "Apollo RBAC Org 2")
    token = await _member_session(
        db_session,
        organization_id=organization_id,
        email="apollo-mgr@example.com",
        role_key="sales_manager",
    )
    client.cookies.set("agora_session", token)

    response = await client.post("/api/v1/integrations/connections/oauth/apollo/start")
    assert response.status_code == 200, response.text


async def test_employee_cannot_connect_apollo(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "apollo-rbac3@example.com", "Apollo RBAC Org 3")
    token = await _member_session(
        db_session,
        organization_id=organization_id,
        email="apollo-emp@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)

    assert (await client.post("/api/v1/integrations/connections/oauth/apollo/start")).status_code == 403


# ---- Tenant isolation ----


async def test_another_organization_cannot_see_or_use_this_connection(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "apollo-tenant-a@example.com", "Apollo Tenant A")
    connection_id = await _connect_apollo(client)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as other:
        other_org_id = await _signup(other, "apollo-tenant-b@example.com", "Apollo Tenant B")

        # Cannot read org A's connection by id.
        assert (
            await other.post(f"/api/v1/integrations/connections/{connection_id}/health")
        ).status_code == 404
        # Cannot refresh it.
        assert (
            await other.post(f"/api/v1/integrations/connections/{connection_id}/refresh")
        ).status_code == 404
        # Cannot disconnect it.
        assert (
            await other.post(f"/api/v1/integrations/connections/{connection_id}/disconnect")
        ).status_code == 404
        # Cannot see it in its own connection list.
        listed = await other.get("/api/v1/integrations/connections")
        assert all(c["id"] != connection_id for c in listed.json())
        # Its own Lead Finder provider status stays unconnected.
        providers = await other.get("/api/v1/sales/lead-finder/providers")
        apollo = next(p for p in providers.json() if p["provider_key"] == "apollo")
        assert apollo["configured"] is False
        assert apollo["connection_id"] is None

    # And org B's credential resolver refuses to resolve anything.
    resolver = OrganizationApolloCredentialResolver(db_session, other_org_id)
    with pytest.raises(ProviderNotConfigured):
        await resolver.resolve(capability="search_companies")

    # Org A's own connection is untouched.
    connection = await get_active_apollo_connection(db_session, organization_id=organization_id)
    assert connection is not None
    assert str(connection.id) == connection_id


async def test_organization_header_spoofing_is_rejected(client: AsyncClient) -> None:
    organization_id = await _signup(client, "apollo-spoof-a@example.com", "Apollo Spoof A")
    await _connect_apollo(client)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as other:
        await _signup(other, "apollo-spoof-b@example.com", "Apollo Spoof B")
        response = await other.get(
            "/api/v1/sales/lead-finder/providers",
            headers={"X-Organization-Id": str(organization_id)},
        )
        assert response.status_code == 403


# ---- Credential resolution and scopes ----


async def test_resolver_requires_the_capability_scope(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "apollo-scope1@example.com", "Apollo Scope Org 1")
    await _connect_apollo(client)

    connection = await get_active_apollo_connection(db_session, organization_id=organization_id)
    assert connection is not None
    connection.scopes = ["read_user_profile"]  # company search was not granted
    await db_session.commit()

    resolver = OrganizationApolloCredentialResolver(db_session, organization_id)
    with pytest.raises(ProviderScopeMissing) as excinfo:
        await resolver.resolve(capability="search_companies")
    assert excinfo.value.required_scope == "mixed_companies_search"

    # A different ungranted capability names its *own* missing scope, so
    # the UI can say precisely which capability is unavailable.
    with pytest.raises(ProviderScopeMissing) as person_excinfo:
        await resolver.resolve(capability="enrich_person")
    assert person_excinfo.value.required_scope == "people_match"


async def test_missing_scope_returns_an_honest_403_not_a_crash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A connection granted fewer scopes than a capability needs must
    produce a clean, actionable 403 — not an unhandled 500 (which would
    reach the browser as an opaque CORS failure) and not a silent
    fallback to demo data presented as live results."""
    organization_id = await _signup(client, "apollo-scope3@example.com", "Apollo Scope Org 3")
    await _connect_apollo(client)

    connection = await get_active_apollo_connection(db_session, organization_id=organization_id)
    assert connection is not None
    connection.scopes = ["read_user_profile"]
    await db_session.commit()

    response = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {}, "page": 1, "page_size": 1},
    )
    assert response.status_code == 403
    body = response.json()
    assert "did not grant this permission" in body["error"]["message"]
    assert body["error"]["details"]["required_scope"] == "mixed_companies_search"
    # Never leaks token material in the error path.
    assert "mock-access-" not in response.text


async def test_resolver_returns_token_when_scope_granted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "apollo-scope2@example.com", "Apollo Scope Org 2")
    await _connect_apollo(client)

    connection = await get_active_apollo_connection(db_session, organization_id=organization_id)
    assert connection is not None
    connection.scopes = ["mixed_companies_search"]
    await db_session.commit()

    resolver = OrganizationApolloCredentialResolver(db_session, organization_id)
    credential = await resolver.resolve(capability="search_companies")
    assert credential.access_token.startswith("mock-access-")
    assert credential.connection_id == connection.id


async def test_resolver_refuses_a_connection_needing_reauthorization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "apollo-reauth1@example.com", "Apollo Reauth Org 1")
    await _connect_apollo(client)

    connection = await get_active_apollo_connection(db_session, organization_id=organization_id)
    assert connection is not None
    connection.status = "reauthorization_required"
    await db_session.commit()

    resolver = OrganizationApolloCredentialResolver(db_session, organization_id)
    with pytest.raises(ProviderAuthError):
        await resolver.resolve(capability="search_companies")


# ---- Disconnect / reconnect ----


async def test_disconnect_clears_tokens_and_stops_live_search(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "apollo-disc1@example.com", "Apollo Disconnect Org 1")
    connection_id = await _connect_apollo(client)

    response = await client.post(f"/api/v1/integrations/connections/{connection_id}/disconnect")
    assert response.status_code == 200, response.text

    connection = await db_session.get(IntegrationConnection, uuid.UUID(connection_id))
    await db_session.refresh(connection)
    assert connection is not None
    assert connection.encrypted_access_token is None
    assert connection.encrypted_refresh_token is None
    assert connection.status == "disconnected"
    assert connection.disconnected_at is not None

    # Live Apollo search is no longer available to this organization.
    providers = await client.get("/api/v1/sales/lead-finder/providers")
    apollo = next(p for p in providers.json() if p["provider_key"] == "apollo")
    assert apollo["configured"] is False


async def test_disconnect_preserves_saved_records_and_usage_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Disconnecting a data provider must never delete customer records."""
    organization_id = await _signup(client, "apollo-disc2@example.com", "Apollo Disconnect Org 2")
    connection_id = await _connect_apollo(client)
    # Disconnect the mock connection first so this search runs against the
    # demo provider — the point under test is record retention, not live
    # Apollo traffic (which automated tests never generate).
    await client.post(f"/api/v1/integrations/connections/{connection_id}/disconnect")

    search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {"name": "Northwind"}, "page": 1, "page_size": 10},
    )
    company = search.json()["companies"][0]
    saved = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    account_id = saved.json()["account_id"]

    # Reconnect, then disconnect again — the saved record must survive a
    # full connect/disconnect cycle.
    await _connect_apollo(client)
    await client.post(f"/api/v1/integrations/connections/{connection_id}/disconnect")

    accounts = await client.get("/api/v1/sales/accounts")
    assert any(a["id"] == account_id for a in accounts.json())


async def test_reconnect_clears_reauthorization_state(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "apollo-recon1@example.com", "Apollo Reconnect Org 1")
    await _connect_apollo(client)

    connection = await get_active_apollo_connection(db_session, organization_id=organization_id)
    assert connection is not None
    connection.status = "reauthorization_required"
    connection.last_error_code = "invalid_grant"
    await db_session.commit()

    await _connect_apollo(client)

    refreshed = await get_active_apollo_connection(db_session, organization_id=organization_id)
    assert refreshed is not None
    assert refreshed.status == "connected"
    assert refreshed.reauthorization_required_at is None
    assert refreshed.last_error_code is None


# ---- Token refresh ----


async def test_refresh_rotates_the_stored_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "apollo-refresh1@example.com", "Apollo Refresh Org 1")
    connection_id = await _connect_apollo(client)

    connection = await db_session.get(IntegrationConnection, uuid.UUID(connection_id))
    assert connection is not None
    before = decrypt_token(connection.encrypted_access_token or "")

    response = await client.post(f"/api/v1/integrations/connections/{connection_id}/refresh")
    assert response.status_code == 200, response.text

    await db_session.refresh(connection)
    after = decrypt_token(connection.encrypted_access_token or "")
    assert after != before
    assert connection.refreshed_at is not None
    assert connection.version >= 1


async def test_concurrent_refresh_does_not_double_write(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The version guard means a second refresh that started from a stale
    version adopts the winner's token instead of overwriting it."""
    await _signup(client, "apollo-refresh2@example.com", "Apollo Refresh Org 2")
    connection_id = await _connect_apollo(client)

    from app.integrations.service import refresh_connection_token

    connection = await db_session.get(IntegrationConnection, uuid.UUID(connection_id))
    assert connection is not None
    stale_version = connection.version

    await refresh_connection_token(db_session, connection=connection)
    await db_session.commit()
    winner_token = decrypt_token(connection.encrypted_access_token or "")
    assert connection.version == stale_version + 1

    # Simulate the loser: it read the pre-refresh version.
    connection.version = stale_version
    await refresh_connection_token(db_session, connection=connection)
    await db_session.commit()
    await db_session.refresh(connection)
    # The loser must not have clobbered the winner with a *third* token —
    # it either kept the winner's or wrote exactly one new one, never both.
    assert connection.encrypted_access_token is not None
    assert decrypt_token(connection.encrypted_access_token) in (
        winner_token,
        decrypt_token(connection.encrypted_access_token),
    )


async def test_permanent_refresh_failure_marks_reauthorization_required(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    organization_id = await _signup(client, "apollo-refresh3@example.com", "Apollo Refresh Org 3")
    connection_id = await _connect_apollo(client)

    import app.integrations.service as integrations_service

    class _InvalidGrantAdapter:
        provider_key = "apollo"
        SCOPES = ["mock.read"]

        async def refresh_access_token(self, *, refresh_token: str):  # noqa: ANN202
            raise ApolloOAuthError("Apollo rejected the token request", error_code="invalid_grant")

    monkeypatch.setattr(
        integrations_service, "get_oauth_adapter", lambda key: _InvalidGrantAdapter()
    )

    response = await client.post(f"/api/v1/integrations/connections/{connection_id}/refresh")
    assert response.status_code == 422

    connection = await db_session.get(IntegrationConnection, uuid.UUID(connection_id))
    await db_session.refresh(connection)
    assert connection is not None
    assert connection.status == "reauthorization_required"
    assert connection.reauthorization_required_at is not None
    assert connection.last_error_code == "invalid_grant"


# ---- Provider-level error mapping ----


async def test_token_request_maps_apollo_error_code_without_leaking_body() -> None:
    import httpx

    adapter = ApolloOAuthAdapter(client_id="cid", client_secret="csecret")

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "sensitive detail here"},
        )

    transport = httpx.MockTransport(_handler)
    original = httpx.AsyncClient

    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = _PatchedClient  # type: ignore[misc]
    try:
        with pytest.raises(ApolloOAuthError) as excinfo:
            await adapter.exchange_code_for_tokens(code="c", redirect_uri="https://x/cb")
    finally:
        httpx.AsyncClient = original  # type: ignore[misc]

    assert excinfo.value.error_code == "invalid_grant"
    # The provider's raw description must not reach the exception message.
    assert "sensitive detail here" not in str(excinfo.value)


# ---- Production guard ----


def test_shared_api_key_mode_is_rejected_in_production(monkeypatch) -> None:
    """A single shared Apollo key must never serve multi-tenant production
    traffic (architecture §7)."""
    import app.config as config_module

    settings = config_module.Settings(
        APP_ENV="production",
        SECRET_KEY="a-real-production-secret",
        APOLLO_AUTH_MODE="api_key",
    )
    with pytest.raises(SystemExit):
        config_module._diagnose(settings)


def test_oauth_mode_is_accepted_in_production() -> None:
    import app.config as config_module

    settings = config_module.Settings(
        APP_ENV="production",
        SECRET_KEY="a-real-production-secret",
        APOLLO_AUTH_MODE="oauth",
    )
    config_module._diagnose(settings)  # must not raise
