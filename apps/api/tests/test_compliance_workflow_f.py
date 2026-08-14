"""Trust Center, end to end.

Draft -> approved content -> published -> public view.

The Trust Center is the only part of this product that speaks to people
outside the organization, which inverts the usual risk: elsewhere an
overstated claim misleads the customer who wrote it, here it misleads
*their* customers, who have no way to check. The tests below are mostly
about what the system refuses to publish.
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


async def _signup(client: AsyncClient, email: str) -> str:
    slug_seed = uuid.uuid4().hex[:6]
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Trust Tester",
            "organization_name": f"Acme AI {slug_seed}",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["organization"]["slug"]


async def _file(client: AsyncClient, name: str) -> str:
    response = await client.post(
        "/api/v1/files/upload-url",
        json={"filename": name, "content_type": "application/pdf", "size_bytes": 2048},
    )
    assert response.status_code == 200, response.text
    return response.json()["file_id"]


async def test_certification_claim_is_refused_without_an_attestation(
    client: AsyncClient,
) -> None:
    """F7, and the point of this workflow. Every control being implemented
    does not make an organization certified — only an auditor does, and
    the system must never bridge that gap on its own."""
    await _signup(client, "trust-cert@example.com")

    response = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "compliance_roadmap",
            "title": "ISO 27001",
            "status": "certified",
            "is_public": True,
        },
    )
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "certificate" in message.lower()
    assert "cannot be inferred" in message.lower()


async def test_independently_assessed_also_requires_an_attestation(
    client: AsyncClient,
) -> None:
    """Both statuses assert an external party's conclusion, so both are
    gated. Only gating "certified" would leave the obvious workaround."""
    await _signup(client, "trust-assessed@example.com")
    response = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "compliance_roadmap",
            "title": "SOC 2",
            "status": "independently_assessed",
        },
    )
    assert response.status_code == 422


async def test_attestation_must_say_what_it_covers(client: AsyncClient) -> None:
    """A certificate with no scope note invites a reader to assume the
    broadest possible reading — a scoped report and a full certification
    look identical once summarised to one word."""
    await _signup(client, "trust-scope@example.com")
    file_id = await _file(client, "iso-cert.pdf")

    response = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "compliance_roadmap",
            "title": "ISO 27001",
            "status": "certified",
            "attestation_file_id": file_id,
        },
    )
    assert response.status_code == 422
    assert "scoped report" in response.json()["error"]["message"]


async def test_certification_is_accepted_with_evidence_and_scope(
    client: AsyncClient,
) -> None:
    await _signup(client, "trust-ok@example.com")
    file_id = await _file(client, "iso-cert.pdf")

    response = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "compliance_roadmap",
            "title": "ISO 27001",
            "status": "certified",
            "is_public": True,
            "attestation_file_id": file_id,
            "attestation_note": "Issued by Nordic Assurance Partners, covering the platform.",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "certified"
    assert body["attested_at"] is not None


async def test_dropping_below_a_certification_clears_its_attestation(
    client: AsyncClient,
) -> None:
    """A stale certificate must not linger against a status that no longer
    claims one."""
    await _signup(client, "trust-downgrade@example.com")
    file_id = await _file(client, "iso-cert.pdf")
    await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "compliance_roadmap",
            "title": "ISO 27001",
            "status": "certified",
            "attestation_file_id": file_id,
            "attestation_note": "Issued by Nordic Assurance Partners.",
        },
    )

    downgraded = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "compliance_roadmap",
            "title": "ISO 27001",
            "status": "planned",
        },
    )
    assert downgraded.status_code == 201
    assert downgraded.json()["attested_at"] is None


async def test_publishing_an_entry_linked_to_a_draft_policy_is_refused(
    client: AsyncClient,
) -> None:
    """F9. A draft policy has not been agreed internally, so publishing it
    externally publishes something nobody signed off."""
    await _signup(client, "trust-draft@example.com")
    policy_id = (
        await client.post(
            "/api/v1/compliance/policies", json={"title": "Draft AI Governance Policy"}
        )
    ).json()["id"]

    response = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "responsible_ai",
            "title": "AI Governance Program",
            "status": "in_progress",
            "is_public": True,
            "policy_id": policy_id,
        },
    )
    assert response.status_code == 422
    assert "still a draft" in response.json()["error"]["message"]


async def test_implemented_status_needs_no_attestation(client: AsyncClient) -> None:
    """"Implemented" describes our own work, which a reader can weigh
    against the rest of the page. Gating it would make the Trust Center
    unusable for the things it is actually for."""
    await _signup(client, "trust-implemented@example.com")
    response = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Security Overview",
            "content": "Access control, MFA, encryption in transit and at rest.",
            "status": "implemented",
            "is_public": True,
        },
    )
    assert response.status_code == 201, response.text


async def test_public_view_shows_only_published_entries(client: AsyncClient) -> None:
    """F11. Anything not explicitly made public stays internal."""
    slug = await _signup(client, "trust-public@example.com")
    await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Security Overview",
            "status": "implemented",
            "is_public": True,
        },
    )
    await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "vulnerability_reporting",
            "title": "Internal only",
            "content": "Draft wording, not for customers.",
            "status": "in_progress",
            "is_public": False,
        },
    )

    public = (await client.get(f"/api/v1/trust-center/public/{slug}")).json()
    categories = {item["category"] for item in public["items"]}
    assert "security_overview" in categories
    assert "vulnerability_reporting" not in categories
    assert "Draft wording" not in str(public)


async def test_public_view_needs_no_session(client: AsyncClient) -> None:
    """It is a public page. If it only rendered for authenticated users it
    would not be doing its job."""
    slug = await _signup(client, "trust-anon@example.com")
    await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Security Overview",
            "status": "implemented",
            "is_public": True,
        },
    )
    await client.post("/api/v1/auth/logout")

    response = await client.get(f"/api/v1/trust-center/public/{slug}")
    assert response.status_code == 200
    assert response.json()["items"]


async def test_another_organizations_file_cannot_back_a_claim(
    client: AsyncClient,
) -> None:
    await _signup(client, "trust-iso-a@example.com")
    file_id = await _file(client, "someone-elses-cert.pdf")
    await client.post("/api/v1/auth/logout")

    await _signup(client, "trust-iso-b@example.com")
    response = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "compliance_roadmap",
            "title": "ISO 27001",
            "status": "certified",
            "attestation_file_id": file_id,
            "attestation_note": "Borrowed certificate.",
        },
    )
    assert response.status_code == 422


async def test_trust_center_changes_are_audited(client: AsyncClient) -> None:
    """F12."""
    await _signup(client, "trust-audit@example.com")
    await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Security Overview",
            "status": "implemented",
            "is_public": True,
        },
    )
    events = (
        await client.get("/api/v1/audit-events?action_prefix=trust_center&limit=20")
    ).json()
    assert "trust_center.item.upserted" in {e["action"] for e in events}
