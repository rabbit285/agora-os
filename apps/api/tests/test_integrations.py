from __future__ import annotations

import hashlib
import hmac
import uuid
from urllib.parse import parse_qs, urlparse

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership, MembershipRole
from app.core.rbac import get_system_role
from app.identity.models import User
from app.identity.service import create_session
from app.main import app
from app.security import hash_password


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _signup(client: AsyncClient, email: str, org_name: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Integrations Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


async def _create_member_with_role(
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


async def _create_workflow(client: AsyncClient, *, name: str, trigger_type: str = "manual") -> str:
    response = await client.post(
        "/api/v1/automation/workflows",
        json={
            "name": name,
            "trigger_type": trigger_type,
            "steps": [{"step_type": "create_task", "config": {"title": "Follow up"}}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


async def _activate_workflow(client: AsyncClient, workflow_id: str) -> None:
    response = await client.patch(
        f"/api/v1/automation/workflows/{workflow_id}/status", json={"status": "active"}
    )
    assert response.status_code == 200, response.text


async def test_org_admin_can_create_connection(client: AsyncClient) -> None:
    await _signup(client, "conn1@example.com", "Connection Org")
    response = await client.post("/api/v1/integrations/connections", json={"name": "My Webhook"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["connector_key"] == "webhook"
    assert body["status"] == "active"
    assert len(body["webhook_secret"]) == 64


async def test_employee_role_cannot_create_connection(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "conn2@example.com", "Connection Org 2")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="employee-conn@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)

    response = await client.post("/api/v1/integrations/connections", json={"name": "Should fail"})
    assert response.status_code == 403


async def test_cannot_link_connection_to_non_webhook_workflow(client: AsyncClient) -> None:
    await _signup(client, "conn3@example.com", "Connection Org 3")
    workflow_id = await _create_workflow(client, name="Manual workflow")  # default trigger_type

    connection = await client.post("/api/v1/integrations/connections", json={"name": "Bad link"})
    connection_id = connection.json()["id"]

    response = await client.patch(
        f"/api/v1/integrations/connections/{connection_id}",
        json={"linked_workflow_id": workflow_id},
    )
    assert response.status_code == 422


async def test_verified_webhook_triggers_linked_workflow(client: AsyncClient) -> None:
    await _signup(client, "conn4@example.com", "Connection Org 4")
    workflow_id = await _create_workflow(client, name="Webhook workflow", trigger_type="webhook")
    await _activate_workflow(client, workflow_id)

    connection = await client.post("/api/v1/integrations/connections", json={"name": "Lead intake"})
    connection_id = connection.json()["id"]
    secret = connection.json()["webhook_secret"]

    link = await client.patch(
        f"/api/v1/integrations/connections/{connection_id}",
        json={"linked_workflow_id": workflow_id},
    )
    assert link.status_code == 200
    assert link.json()["linked_workflow_id"] == workflow_id

    body = b'{"lead_name": "Test Lead"}'
    signature = _sign(secret, body)
    received = await client.post(
        f"/api/v1/integrations/webhooks/{connection_id}/receive",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )
    assert received.status_code == 202, received.text
    assert received.json() == {"received": True, "verified": True}

    events = await client.get(f"/api/v1/integrations/connections/{connection_id}/events")
    assert events.status_code == 200
    assert len(events.json()) == 1
    event = events.json()[0]
    assert event["verified"] is True
    assert event["triggered_run_id"] is not None

    runs = await client.get("/api/v1/automation/runs")
    assert runs.status_code == 200
    matching_run = next(r for r in runs.json() if r["id"] == event["triggered_run_id"])
    assert matching_run["workflow_id"] == workflow_id
    # Execution is Temporal-durable (spec §61) — the row is created
    # synchronously but its steps run via a worker, never inline here.
    assert matching_run["status"] == "running"
    assert matching_run["trigger_payload"] == {"lead_name": "Test Lead"}


async def test_invalid_signature_does_not_trigger_workflow(client: AsyncClient) -> None:
    await _signup(client, "conn5@example.com", "Connection Org 5")
    workflow_id = await _create_workflow(client, name="Webhook workflow 2", trigger_type="webhook")
    await _activate_workflow(client, workflow_id)

    connection = await client.post(
        "/api/v1/integrations/connections", json={"name": "Lead intake 2"}
    )
    connection_id = connection.json()["id"]

    await client.patch(
        f"/api/v1/integrations/connections/{connection_id}",
        json={"linked_workflow_id": workflow_id},
    )

    body = b'{"lead_name": "Forged Lead"}'
    received = await client.post(
        f"/api/v1/integrations/webhooks/{connection_id}/receive",
        content=body,
        headers={"X-Webhook-Signature": "not-the-real-signature"},
    )
    assert received.status_code == 202
    assert received.json() == {"received": True, "verified": False}

    events = await client.get(f"/api/v1/integrations/connections/{connection_id}/events")
    event = events.json()[0]
    assert event["verified"] is False
    assert event["triggered_run_id"] is None

    runs = await client.get("/api/v1/automation/runs")
    assert runs.json() == []


async def test_disabled_connection_rejects_valid_signature(client: AsyncClient) -> None:
    await _signup(client, "conn6@example.com", "Connection Org 6")
    connection = await client.post(
        "/api/v1/integrations/connections", json={"name": "Will be disabled"}
    )
    connection_id = connection.json()["id"]
    secret = connection.json()["webhook_secret"]

    disable = await client.patch(
        f"/api/v1/integrations/connections/{connection_id}", json={"status": "disabled"}
    )
    assert disable.status_code == 200
    assert disable.json()["status"] == "disabled"

    body = b'{"lead_name": "Anyone"}'
    received = await client.post(
        f"/api/v1/integrations/webhooks/{connection_id}/receive",
        content=body,
        headers={"X-Webhook-Signature": _sign(secret, body)},
    )
    assert received.status_code == 202
    assert received.json()["verified"] is False


async def test_receive_webhook_for_unknown_connection_returns_not_found(
    client: AsyncClient,
) -> None:
    await _signup(client, "conn7@example.com", "Connection Org 7")
    response = await client.post(
        f"/api/v1/integrations/webhooks/{uuid.uuid4()}/receive",
        content=b"{}",
        headers={"X-Webhook-Signature": "irrelevant"},
    )
    assert response.status_code == 404


async def test_provider_catalog_reports_hubspot_not_configured(client: AsyncClient) -> None:
    await _signup(client, "provcat1@example.com", "Provider Catalog Org")
    response = await client.get("/api/v1/integrations/providers")
    assert response.status_code == 200
    catalog = {p["connector_key"]: p for p in response.json()}
    assert catalog["webhook"]["configured"] is True
    # No real HUBSPOT_CLIENT_ID/SECRET exist in this test environment —
    # the catalog must report this honestly rather than claim a fake connection.
    assert catalog["hubspot"]["configured"] is False
    assert catalog["hubspot"]["auth_type"] == "oauth2"


async def test_provider_catalog_lists_all_six_oauth_providers_with_scope_previews(
    client: AsyncClient,
) -> None:
    await _signup(client, "provcat2@example.com", "Provider Catalog Org 2")
    response = await client.get("/api/v1/integrations/providers")
    assert response.status_code == 200
    catalog = {p["connector_key"]: p for p in response.json()}

    for key in ("hubspot", "google", "microsoft", "github", "slack", "salesforce"):
        assert catalog[key]["auth_type"] == "oauth2"
        # None of these have real credentials in this environment — every
        # one must report Not-configured honestly, never a fake connection.
        assert catalog[key]["configured"] is False
        assert len(catalog[key]["scopes"]) > 0


async def test_employee_role_cannot_start_oauth(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "oauth-emp1@example.com", "OAuth Employee Org")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee-oauth@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.post("/api/v1/integrations/connections/oauth/hubspot/start")
    assert response.status_code == 403


async def _start_hubspot_oauth(client: AsyncClient) -> tuple[str, str]:
    """Starts the flow and returns (connection_id, state) — the mock
    adapter (no real HUBSPOT_CLIENT_ID/SECRET in this test env) embeds
    state as a query parameter in its fake authorization_url."""
    started = await client.post("/api/v1/integrations/connections/oauth/hubspot/start")
    assert started.status_code == 200, started.text
    body = started.json()
    parsed = urlparse(body["authorization_url"])
    state = parse_qs(parsed.query)["state"][0]
    return body["connection_id"], state


async def test_start_oauth_flow_returns_authorization_url(client: AsyncClient) -> None:
    await _signup(client, "oauth1@example.com", "OAuth Org 1")
    connection_id, state = await _start_hubspot_oauth(client)
    assert connection_id
    assert state

    connections = await client.get("/api/v1/integrations/connections")
    matching = next(c for c in connections.json() if c["id"] == connection_id)
    assert matching["connector_key"] == "hubspot"
    assert matching["status"] == "not_connected"


async def test_oauth_callback_connects_and_checks_health(client: AsyncClient) -> None:
    await _signup(client, "oauth2@example.com", "OAuth Org 2")
    connection_id, state = await _start_hubspot_oauth(client)

    callback = await client.get(
        "/api/v1/integrations/connections/oauth/hubspot/callback",
        params={"code": "fake-code", "state": state},
    )
    assert callback.status_code in (302, 307)
    assert "connected=hubspot" in callback.headers["location"]

    connections = await client.get("/api/v1/integrations/connections")
    matching = next(c for c in connections.json() if c["id"] == connection_id)
    assert matching["status"] == "connected"
    assert matching["health_status"] == "ok"
    assert matching["external_account_id"] == "mock-hubspot-account-0001"
    assert matching["scopes"] == ["mock.read"]


async def test_oauth_callback_with_unknown_state_redirects_with_error(client: AsyncClient) -> None:
    await _signup(client, "oauth3@example.com", "OAuth Org 3")
    callback = await client.get(
        "/api/v1/integrations/connections/oauth/hubspot/callback",
        params={"code": "fake-code", "state": "not-a-real-state"},
    )
    assert callback.status_code in (302, 307)
    assert "error=" in callback.headers["location"]


async def test_refresh_health_sync_and_disconnect_lifecycle(client: AsyncClient) -> None:
    await _signup(client, "oauth4@example.com", "OAuth Org 4")
    connection_id, state = await _start_hubspot_oauth(client)
    await client.get(
        "/api/v1/integrations/connections/oauth/hubspot/callback",
        params={"code": "fake-code", "state": state},
    )

    refreshed = await client.post(f"/api/v1/integrations/connections/{connection_id}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "connected"

    health = await client.post(f"/api/v1/integrations/connections/{connection_id}/health")
    assert health.status_code == 200
    assert health.json()["health_status"] == "ok"

    # Sync is fired off as a durable Temporal workflow (IntegrationSyncWorkflow)
    # rather than run inline — the endpoint only creates the SyncRun row and
    # kicks off the workflow (a no-op in tests, see conftest's sync-starter
    # override), so it comes back "running", not "succeeded". The real
    # execution path is exercised directly in
    # test_execute_sync_run_against_mock_adapter_succeeds below, the same
    # split test_knowledge.py uses for ingest_document vs. the upload route.
    synced = await client.post(f"/api/v1/integrations/connections/{connection_id}/sync")
    assert synced.status_code == 200
    assert synced.json()["status"] == "running"

    sync_runs = await client.get(f"/api/v1/integrations/connections/{connection_id}/sync-runs")
    assert sync_runs.status_code == 200
    assert len(sync_runs.json()) == 1

    disconnected = await client.post(f"/api/v1/integrations/connections/{connection_id}/disconnect")
    assert disconnected.status_code == 200
    assert disconnected.json()["status"] == "disconnected"
    assert disconnected.json()["health_status"] is None


async def test_execute_sync_run_against_mock_adapter_succeeds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.integrations.models import IntegrationConnection as _Connection
    from app.integrations.service import run_sync

    await _signup(client, "oauth-sync1@example.com", "OAuth Sync Org 1")
    connection_id, state = await _start_hubspot_oauth(client)
    await client.get(
        "/api/v1/integrations/connections/oauth/hubspot/callback",
        params={"code": "fake-code", "state": state},
    )

    connection = await db_session.get(_Connection, uuid.UUID(connection_id))
    assert connection is not None
    sync_run = await run_sync(db_session, connection=connection)
    await db_session.commit()

    assert sync_run.status == "succeeded"
    assert sync_run.items_synced == 3
    assert sync_run.completed_at is not None

    # execute_sync_run also handles a failing adapter honestly rather than
    # silently succeeding.
    class _FailingAdapter:
        provider_key = "hubspot"
        SCOPES: list[str] = []

        async def sync(self, *, access_token: str) -> None:
            raise RuntimeError("simulated provider outage")

    import app.integrations.service as integrations_service

    original_get_adapter = integrations_service.get_oauth_adapter
    integrations_service.get_oauth_adapter = lambda connector_key: _FailingAdapter()  # type: ignore[assignment]
    try:
        failing_run = await run_sync(db_session, connection=connection)
    finally:
        integrations_service.get_oauth_adapter = original_get_adapter
    assert failing_run.status == "failed"
    assert failing_run.error is not None


async def test_generic_oauth_flow_works_for_a_non_hubspot_provider(client: AsyncClient) -> None:
    """Proves the OAuth framework is genuinely provider-neutral rather than
    hardcoded to HubSpot: starting/completing a flow for Google (also
    unconfigured, also mock-backed in this environment) goes through the
    exact same generic endpoints and service functions."""
    await _signup(client, "oauth-google1@example.com", "OAuth Google Org 1")

    started = await client.post("/api/v1/integrations/connections/oauth/google/start")
    assert started.status_code == 200, started.text
    parsed = urlparse(started.json()["authorization_url"])
    state = parse_qs(parsed.query)["state"][0]
    connection_id = started.json()["connection_id"]

    callback = await client.get(
        "/api/v1/integrations/connections/oauth/google/callback",
        params={"code": "fake-code", "state": state},
    )
    assert callback.status_code in (302, 307)
    assert "connected=google" in callback.headers["location"]

    connections = await client.get("/api/v1/integrations/connections")
    matching = next(c for c in connections.json() if c["id"] == connection_id)
    assert matching["connector_key"] == "google"
    assert matching["status"] == "connected"
    assert matching["external_account_id"] == "mock-google-account-0001"


async def test_unknown_oauth_provider_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "oauth-unknown1@example.com", "OAuth Unknown Org 1")
    response = await client.post("/api/v1/integrations/connections/oauth/not-a-provider/start")
    assert response.status_code == 404


async def test_oauth_lifecycle_records_audit_events(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from sqlalchemy import select as _select

    from app.audit.models import AuditEvent
    from app.integrations.models import IntegrationConnection as _Connection
    from app.integrations.service import run_sync

    await _signup(client, "oauth-audit1@example.com", "OAuth Audit Org 1")
    connection_id, state = await _start_hubspot_oauth(client)
    await client.get(
        "/api/v1/integrations/connections/oauth/hubspot/callback",
        params={"code": "fake-code", "state": state},
    )
    await client.post(f"/api/v1/integrations/connections/{connection_id}/refresh")

    connection = await db_session.get(_Connection, uuid.UUID(connection_id))
    assert connection is not None
    await run_sync(db_session, connection=connection)
    await db_session.commit()

    await client.post(f"/api/v1/integrations/connections/{connection_id}/disconnect")

    events = (
        (
            await db_session.execute(
                _select(AuditEvent.action).where(AuditEvent.object_id == connection_id)
            )
        )
        .scalars()
        .all()
    )
    actions = set(events)
    assert "integrations.oauth.started" in actions
    assert "integrations.oauth.connected" in actions
    assert "integrations.oauth.refreshed" in actions
    assert "integrations.oauth.disconnected" in actions


async def test_oauth_connection_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-oauth1@example.com", "Cross OAuth Org 1")
    connection_id, _ = await _start_hubspot_oauth(client)

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(other_client, "cross-oauth2@example.com", "Cross OAuth Org 2")

    response = await other_client.post(
        f"/api/v1/integrations/connections/{connection_id}/health",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()
