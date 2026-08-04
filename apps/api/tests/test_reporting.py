"""Tests for the Reporting module (spec §65, PLAT-20). Every report type
computes real, live-queried organizational data (never a canned/sample
document) and is rendered into a genuinely openable file in object
storage — these tests generate real files and read the actual bytes back
via `app.core.storage.download_object`, not just check that a 201 came
back.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Reporting Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_report_types_lists_all_14_spec_named_types(client: AsyncClient) -> None:
    await _signup(client, "report1@example.com", "Reporting Org 1")
    response = await client.get("/api/v1/reports/types")
    assert response.status_code == 200
    keys = {rt["key"] for rt in response.json()}
    assert keys == {
        "executive_business_ai",
        "compliance",
        "security_posture",
        "gdpr",
        "eu_ai_act",
        "ai_inventory",
        "risk",
        "vendor",
        "sales_performance",
        "pipeline",
        "support_performance",
        "automation_roi",
        "audit_evidence_pack",
        "board",
    }


@pytest.mark.parametrize("fmt", ["pdf", "docx", "xlsx", "csv"])
async def test_generate_report_completes_for_every_format(client: AsyncClient, fmt: str) -> None:
    await _signup(client, f"report-{fmt}@example.com", f"Reporting Org {fmt}")
    response = await client.post(
        "/api/v1/reports", json={"report_type": "board", "format": fmt}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["error_message"] is None


async def test_generate_report_rejects_unknown_report_type(client: AsyncClient) -> None:
    await _signup(client, "report-badtype@example.com", "Reporting Org Bad Type")
    response = await client.post(
        "/api/v1/reports", json={"report_type": "not_a_real_type", "format": "pdf"}
    )
    assert response.status_code == 422


async def test_generate_report_rejects_unknown_format(client: AsyncClient) -> None:
    await _signup(client, "report-badformat@example.com", "Reporting Org Bad Format")
    response = await client.post(
        "/api/v1/reports", json={"report_type": "board", "format": "rtf"}
    )
    assert response.status_code == 422


async def test_download_returns_a_secure_link_for_a_completed_report(client: AsyncClient) -> None:
    await _signup(client, "report-download@example.com", "Reporting Org Download")
    created = await client.post(
        "/api/v1/reports", json={"report_type": "board", "format": "pdf"}
    )
    report_id = created.json()["id"]

    response = await client.get(f"/api/v1/reports/{report_id}/download")
    assert response.status_code == 200
    assert response.json()["download_url"].startswith("http")


async def test_reports_are_tenant_isolated(client: AsyncClient) -> None:
    await _signup(client, "report-tenant-a@example.com", "Reporting Org Tenant A")
    created = await client.post(
        "/api/v1/reports", json={"report_type": "board", "format": "pdf"}
    )
    report_id = created.json()["id"]

    await client.post("/api/v1/auth/logout")
    await _signup(client, "report-tenant-b@example.com", "Reporting Org Tenant B")

    response = await client.get(f"/api/v1/reports/{report_id}")
    assert response.status_code == 404

    other_org_reports = await client.get("/api/v1/reports")
    assert other_org_reports.json() == []


async def test_risk_report_reflects_a_real_risk_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.core.storage import download_object
    from app.reporting.models import Report

    await _signup(client, "report-risk@example.com", "Reporting Org Risk")
    created_risk = await client.post(
        "/api/v1/compliance/risks",
        json={
            "title": "Unencrypted backup bucket",
            "category": "security",
            "likelihood": "high",
            "impact": "high",
        },
    )
    assert created_risk.status_code == 201, created_risk.text

    generated = await client.post(
        "/api/v1/reports", json={"report_type": "risk", "format": "csv"}
    )
    assert generated.status_code == 201, generated.text
    assert generated.json()["status"] == "completed"

    report = (
        await db_session.execute(select(Report).where(Report.id == uuid.UUID(generated.json()["id"])))
    ).scalar_one()
    assert report.storage_key is not None
    content = download_object(report.storage_key).decode("utf-8")
    assert "Unencrypted backup bucket" in content
    assert "high" in content


async def test_failed_report_status_is_persisted_not_silently_swallowed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.reporting.content as content_module

    async def _boom(db, organization_id):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated aggregation failure")

    monkeypatch.setitem(content_module.REPORT_BUILDERS, "board", _boom)

    await _signup(client, "report-fail@example.com", "Reporting Org Fail")
    response = await client.post(
        "/api/v1/reports", json={"report_type": "board", "format": "pdf"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert "simulated aggregation failure" in body["error_message"]
