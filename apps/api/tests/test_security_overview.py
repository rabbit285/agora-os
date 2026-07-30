from __future__ import annotations

from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Overview Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text


async def test_overview_is_all_zero_for_a_fresh_org(client: AsyncClient) -> None:
    await _signup(client, "overview1@example.com", "Overview Org 1")

    response = await client.get("/api/v1/security/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["security_score"] == 100
    assert body["critical_alerts"] == 0
    assert body["high_risks"] == 0
    assert body["assets_monitored"] == 0
    assert body["vulnerabilities_open"] == 0
    assert body["identity_issues_open"] == 0
    assert body["cloud_misconfigurations_open"] == 0
    assert body["open_incidents"] == 0
    assert body["evidence_coverage_percent"] == 0.0


async def test_overview_reflects_real_counts(client: AsyncClient) -> None:
    await _signup(client, "overview2@example.com", "Overview Org 2")

    await client.post("/api/v1/security/assets", json={"name": "prod-1", "asset_type": "server"})
    await client.post(
        "/api/v1/security/findings",
        json={"title": "Open CVE", "category": "vulnerability", "severity": "high"},
    )
    await client.post(
        "/api/v1/security/findings",
        json={
            "title": "Public S3 bucket",
            "category": "cloud_misconfiguration",
            "severity": "high",
        },
    )
    await client.post(
        "/api/v1/security/findings",
        json={"title": "No MFA on admin", "category": "identity", "severity": "critical"},
    )
    alert = await client.post(
        "/api/v1/security/alerts", json={"title": "Active exploit attempt", "severity": "critical"}
    )
    assert alert.status_code == 201
    await client.post(
        "/api/v1/security/incidents", json={"title": "Active breach", "severity": "high"}
    )

    response = await client.get("/api/v1/security/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["assets_monitored"] == 1
    assert body["vulnerabilities_open"] == 1
    assert body["cloud_misconfigurations_open"] == 1
    assert body["identity_issues_open"] == 1
    assert body["critical_alerts"] == 1
    assert body["open_incidents"] == 1
    # deduction model: 1 critical alert (10) + 1 critical finding (8) +
    # 2 high findings (4 each = 8) + 1 open incident (6) = 32 deducted
    assert body["security_score"] == 100 - 32


async def test_overview_is_scoped_per_organization(client: AsyncClient) -> None:
    from httpx import ASGITransport

    from app.main import app

    await _signup(client, "overview3@example.com", "Overview Org 3")
    await client.post(
        "/api/v1/security/assets", json={"name": "org3-asset", "asset_type": "server"}
    )

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    await _signup(other_client, "overview4@example.com", "Overview Org 4")

    response = await other_client.get("/api/v1/security/overview")
    assert response.status_code == 200
    assert response.json()["assets_monitored"] == 0
    await other_client.aclose()


async def test_evidence_coverage_counts_incidents_with_linked_evidence(client: AsyncClient) -> None:
    await _signup(client, "overview5@example.com", "Overview Org 5")

    incident = await client.post(
        "/api/v1/security/incidents", json={"title": "Evidence incident", "severity": "high"}
    )
    incident_id = incident.json()["id"]

    no_evidence_incident = await client.post(
        "/api/v1/security/incidents", json={"title": "No evidence incident", "severity": "low"}
    )
    assert no_evidence_incident.status_code == 201

    upload = await client.post(
        "/api/v1/files/upload-url",
        json={"filename": "report.pdf", "content_type": "application/pdf", "size_bytes": 512},
    )
    assert upload.status_code == 200
    file_id = upload.json()["file_id"]

    evidence = await client.post(
        "/api/v1/compliance/evidence",
        json={"title": "Incident report", "file_id": file_id, "incident_id": incident_id},
    )
    assert evidence.status_code == 201

    response = await client.get("/api/v1/security/overview")
    assert response.status_code == 200
    # 1 of 2 incidents has linked evidence
    assert response.json()["evidence_coverage_percent"] == 50.0
