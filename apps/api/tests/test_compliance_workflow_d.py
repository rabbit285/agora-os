"""DSAR, end to end.

Received -> Identity verified -> Data located -> Human review -> Secure
export -> Completed.

The risk here runs opposite to the rest of the module. Elsewhere the
danger is claiming compliance we cannot support; here it is *doing what
we are asked*. An access request asks a controller to hand over
everything it holds about a named person, so answering one without
establishing who is asking discloses one person's data to another. The
request is the attack, and the verification gate is the control.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.seed import _ensure_compliance_catalog


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


async def _signup(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Privacy Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _dsar(client: AsyncClient, email: str = "emma.muller@example-test.com") -> str:
    response = await client.post(
        "/api/v1/compliance/dsars",
        json={
            "requester_name": "Emma Muller",
            "requester_email": email,
            "request_type": "access",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_new_request_starts_unverified(client: AsyncClient) -> None:
    await _signup(client, "dsar-new@example.com")
    dsar_id = await _dsar(client)
    body = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}")).json()
    assert body["verification_status"] == "pending"
    assert body["verified_at"] is None


async def test_export_is_blocked_before_identity_is_verified(client: AsyncClient) -> None:
    """D3, and the reason this workflow exists. Exporting an unverified
    request is a disclosure to whoever asked, not to the data subject."""
    await _signup(client, "dsar-block@example.com")
    dsar_id = await _dsar(client)

    response = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/export")
    assert response.status_code == 409
    message = response.json()["error"]["message"].lower()
    assert "verified" in message
    # The refusal explains the risk rather than just denying, so whoever
    # hits it understands why rather than looking for a way around it.
    assert "wrong person" in message


async def test_export_succeeds_once_verified(client: AsyncClient) -> None:
    await _signup(client, "dsar-export@example.com")
    dsar_id = await _dsar(client)

    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/verify-identity",
        json={"verified": True, "method": "Email verification (synthetic test)"},
    )
    response = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/export")
    assert response.status_code == 200
    body = response.text
    assert "DATA SUBJECT ACCESS REQUEST" in body
    # The package carries how it was produced, so a file separated from
    # this system still says what it did and did not cover.
    assert "Identity verification: verified" in body
    assert "COVERAGE" in body


async def test_failed_verification_still_blocks_export(client: AsyncClient) -> None:
    """A recorded failure must not read as "handled" and open the gate."""
    await _signup(client, "dsar-failed@example.com")
    dsar_id = await _dsar(client)

    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/verify-identity",
        json={"verified": False, "method": "Could not match the address on file"},
    )
    body = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}")).json()
    assert body["verification_status"] == "failed"

    response = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/export")
    assert response.status_code == 409


async def test_discovery_finds_the_person_where_they_actually_appear(
    client: AsyncClient,
) -> None:
    """D5. A discovery that reports nothing regardless of the data is
    worse than none — it manufactures confidence that there is nothing to
    disclose."""
    await _signup(client, "dsar-discover@example.com")

    subject_email = "found.person@example-test.com"
    created = await client.post(
        "/api/v1/support/customers",
        json={"name": "Found Person", "email": subject_email},
    )
    assert created.status_code in (200, 201), created.text

    dsar_id = await _dsar(client, email=subject_email)
    response = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discover")
    assert response.status_code == 200, response.text
    findings = response.json()

    by_source = {s["source"]: s for s in findings["sources"]}
    assert by_source["Support — customers"]["matches"] == 1
    assert findings["total_matches"] >= 1
    # Every result states what was not searched, so nobody reads a clean
    # result as "there is nothing".
    assert "not searched" in findings["coverage_note"]


async def test_discovery_is_scoped_to_the_calling_organization(
    client: AsyncClient,
) -> None:
    """The one thing worse than failing to find a person's data is
    returning somebody else's."""
    subject_email = "shared.address@example-test.com"

    await _signup(client, "dsar-tenant-a@example.com")
    await client.post(
        "/api/v1/support/customers", json={"name": "Tenant A Customer", "email": subject_email}
    )
    await client.post("/api/v1/auth/logout")

    await _signup(client, "dsar-tenant-b@example.com")
    dsar_id = await _dsar(client, email=subject_email)
    findings = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discover")).json()

    by_source = {s["source"]: s for s in findings["sources"]}
    assert by_source["Support — customers"]["matches"] == 0, (
        "another organization's customer record surfaced in this tenant's DSAR discovery"
    )


async def test_discovery_returns_references_not_a_second_copy_of_the_data(
    client: AsyncClient,
) -> None:
    """Counts and ids, not records: the discovery result must not become
    an uncontrolled duplicate of the personal data it located."""
    await _signup(client, "dsar-refs@example.com")
    subject_email = "refs.person@example-test.com"
    await client.post(
        "/api/v1/support/customers", json={"name": "Refs Person", "email": subject_email}
    )
    dsar_id = await _dsar(client, email=subject_email)
    findings = (await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discover")).json()

    serialized = str(findings)
    assert "Refs Person" not in serialized


async def test_another_organizations_dsar_is_not_reachable(client: AsyncClient) -> None:
    await _signup(client, "dsar-iso-a@example.com")
    dsar_id = await _dsar(client)
    await client.post("/api/v1/auth/logout")

    await _signup(client, "dsar-iso-b@example.com")
    for path in ("verify-identity", "discover", "export"):
        body = {"verified": True, "method": "x"} if path == "verify-identity" else None
        response = await client.post(f"/api/v1/compliance/dsars/{dsar_id}/{path}", json=body)
        assert response.status_code == 404, path


async def test_the_whole_request_is_auditable(client: AsyncClient) -> None:
    """D11. Every step that touches someone's personal data leaves a
    record of who did it and when."""
    await _signup(client, "dsar-audit@example.com")
    dsar_id = await _dsar(client)
    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/verify-identity",
        json={"verified": True, "method": "Email verification"},
    )
    await client.post(f"/api/v1/compliance/dsars/{dsar_id}/discover")
    await client.post(f"/api/v1/compliance/dsars/{dsar_id}/export")

    events = (
        await client.get("/api/v1/audit-events?action_prefix=compliance.dsar&limit=50")
    ).json()
    actions = {e["action"] for e in events}
    for expected in (
        "compliance.dsar.identity_verified",
        "compliance.dsar.discovery_run",
        "compliance.dsar.export_generated",
    ):
        assert expected in actions, f"{expected} missing from the audit trail"


async def test_failed_verification_is_audited_too(client: AsyncClient) -> None:
    await _signup(client, "dsar-audit-fail@example.com")
    dsar_id = await _dsar(client)
    await client.post(
        f"/api/v1/compliance/dsars/{dsar_id}/verify-identity",
        json={"verified": False, "method": "Address did not match"},
    )
    events = (
        await client.get("/api/v1/audit-events?action_prefix=compliance.dsar&limit=20")
    ).json()
    assert "compliance.dsar.identity_verification_failed" in {e["action"] for e in events}
