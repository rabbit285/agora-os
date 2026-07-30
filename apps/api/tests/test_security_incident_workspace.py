from __future__ import annotations

from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Workspace Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text


async def test_incident_detail_includes_empty_timeline_and_assets(client: AsyncClient) -> None:
    await _signup(client, "workspace1@example.com", "Workspace Org 1")
    created = await client.post(
        "/api/v1/security/incidents",
        json={"title": "New incident", "severity": "medium"},
    )
    incident_id = created.json()["id"]

    detail = await client.get(f"/api/v1/security/incidents/{incident_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["timeline"] == []
    assert body["affected_assets"] == []
    assert body["root_cause"] is None
    assert body["lessons_learned"] is None


async def test_add_timeline_entry(client: AsyncClient) -> None:
    await _signup(client, "workspace2@example.com", "Workspace Org 2")
    created = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Timeline incident", "severity": "medium"},
    )
    incident_id = created.json()["id"]

    entry = await client.post(
        f"/api/v1/security/incidents/{incident_id}/timeline",
        json={"entry_type": "update", "body": "Contained the affected host."},
    )
    assert entry.status_code == 201
    assert entry.json()["entry_type"] == "update"
    assert entry.json()["body"] == "Contained the affected host."

    comm = await client.post(
        f"/api/v1/security/incidents/{incident_id}/timeline",
        json={"entry_type": "communication", "body": "Notified customer support."},
    )
    assert comm.status_code == 201

    detail = await client.get(f"/api/v1/security/incidents/{incident_id}")
    timeline = detail.json()["timeline"]
    assert len(timeline) == 2
    assert timeline[0]["body"] == "Contained the affected host."
    assert timeline[1]["entry_type"] == "communication"


async def test_link_affected_asset_is_idempotent(client: AsyncClient) -> None:
    await _signup(client, "workspace3@example.com", "Workspace Org 3")
    incident = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Asset-linked incident", "severity": "high"},
    )
    incident_id = incident.json()["id"]

    asset = await client.post(
        "/api/v1/security/assets", json={"name": "prod-web-1", "asset_type": "server"}
    )
    asset_id = asset.json()["id"]

    first = await client.post(
        f"/api/v1/security/incidents/{incident_id}/assets", json={"asset_id": asset_id}
    )
    assert first.status_code == 201
    assert len(first.json()["affected_assets"]) == 1

    second = await client.post(
        f"/api/v1/security/incidents/{incident_id}/assets", json={"asset_id": asset_id}
    )
    assert second.status_code == 201
    assert len(second.json()["affected_assets"]) == 1
    assert second.json()["affected_assets"][0]["id"] == asset_id


async def test_link_affected_asset_from_other_org_is_rejected(client: AsyncClient) -> None:
    await _signup(client, "workspace4@example.com", "Workspace Org 4")
    incident = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Cross-org asset test", "severity": "high"},
    )
    incident_id = incident.json()["id"]

    response = await client.post(
        f"/api/v1/security/incidents/{incident_id}/assets",
        json={"asset_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


async def test_update_incident_postmortem(client: AsyncClient) -> None:
    await _signup(client, "workspace5@example.com", "Workspace Org 5")
    created = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Postmortem incident", "severity": "medium"},
    )
    incident_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/security/incidents/{incident_id}/postmortem",
        json={"root_cause": "Misconfigured firewall rule.", "lessons_learned": "Add a linter."},
    )
    assert updated.status_code == 200
    assert updated.json()["root_cause"] == "Misconfigured firewall rule."
    assert updated.json()["lessons_learned"] == "Add a linter."

    detail = await client.get(f"/api/v1/security/incidents/{incident_id}")
    assert detail.json()["root_cause"] == "Misconfigured firewall rule."


async def test_asset_detail_includes_findings_and_incidents(client: AsyncClient) -> None:
    await _signup(client, "workspace6@example.com", "Workspace Org 6")
    asset = await client.post(
        "/api/v1/security/assets", json={"name": "db-primary", "asset_type": "database"}
    )
    asset_id = asset.json()["id"]

    finding = await client.post(
        "/api/v1/security/findings",
        json={
            "title": "Unpatched CVE",
            "category": "vulnerability",
            "severity": "high",
            "asset_id": asset_id,
        },
    )
    assert finding.status_code == 201

    incident = await client.post(
        "/api/v1/security/incidents", json={"title": "DB incident", "severity": "high"}
    )
    incident_id = incident.json()["id"]
    await client.post(
        f"/api/v1/security/incidents/{incident_id}/assets", json={"asset_id": asset_id}
    )

    detail = await client.get(f"/api/v1/security/assets/{asset_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["findings"]) == 1
    assert body["findings"][0]["title"] == "Unpatched CVE"
    assert len(body["incidents"]) == 1
    assert body["incidents"][0]["id"] == incident_id


async def test_asset_detail_from_other_org_returns_not_found(client: AsyncClient) -> None:
    from httpx import ASGITransport

    from app.main import app

    await _signup(client, "workspace7@example.com", "Workspace Org 7")
    asset = await client.post(
        "/api/v1/security/assets", json={"name": "org7-asset", "asset_type": "server"}
    )
    asset_id = asset.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    await _signup(other_client, "workspace8@example.com", "Workspace Org 8")

    response = await other_client.get(f"/api/v1/security/assets/{asset_id}")
    assert response.status_code == 404
    await other_client.aclose()


async def test_alert_detail_includes_related_finding(client: AsyncClient) -> None:
    await _signup(client, "workspace9@example.com", "Workspace Org 9")
    finding = await client.post(
        "/api/v1/security/findings",
        json={"title": "Brute force pattern", "category": "identity", "severity": "high"},
    )
    finding_id = finding.json()["id"]

    alert = await client.post(
        "/api/v1/security/alerts",
        json={"title": "Repeated failed logins", "severity": "high", "finding_id": finding_id},
    )
    alert_id = alert.json()["id"]

    detail = await client.get(f"/api/v1/security/alerts/{alert_id}")
    assert detail.status_code == 200
    assert detail.json()["finding"]["id"] == finding_id


async def test_alert_detail_without_finding_returns_null(client: AsyncClient) -> None:
    await _signup(client, "workspace10@example.com", "Workspace Org 10")
    alert = await client.post(
        "/api/v1/security/alerts", json={"title": "Standalone alert", "severity": "low"}
    )
    alert_id = alert.json()["id"]

    detail = await client.get(f"/api/v1/security/alerts/{alert_id}")
    assert detail.status_code == 200
    assert detail.json()["finding"] is None
