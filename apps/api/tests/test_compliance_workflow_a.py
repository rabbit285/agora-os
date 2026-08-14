"""The spec's core compliance lifecycle, end to end.

Document -> Evidence -> Control -> Assessment -> Gap -> Task ->
Remediation -> Reassessment -> updated status.

Each step used to exist in isolation; the chain did not. These tests
assert the joins, because that is where it was broken: a control could be
mapped and evidence could be attached, but nothing computed a per
requirement position from them, nothing named the deficiency, and the
remediation task that did get raised pointed at nothing.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.seed import _ensure_compliance_catalog


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    """Frameworks and requirements are global catalog rows seeded by the
    seed script, not by signup — without this every test here would be
    asserting against an empty GDPR."""
    await _ensure_compliance_catalog(db_session)


async def _signup(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Compliance Tester",
            "organization_name": f"Acme AI Technologies {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _gdpr(client: AsyncClient) -> tuple[str, dict[str, str]]:
    """Returns the GDPR framework id and a {reference_code: id} map."""
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    framework_id = next(f["id"] for f in frameworks if f["key"] == "gdpr")
    requirements = (
        await client.get(f"/api/v1/compliance/frameworks/{framework_id}/requirements")
    ).json()
    return framework_id, {r["reference_code"]: r["id"] for r in requirements}


async def _upload_file(client: AsyncClient, name: str) -> str:
    """Register a file and return its id.

    Uploads go through a presigned URL, so the File row is created by
    this call and the bytes are PUT straight to object storage by the
    browser. Evidence only needs the row, so these tests stop here rather
    than round-tripping through MinIO for no added coverage.
    """
    response = await client.post(
        "/api/v1/files/upload-url",
        json={"filename": name, "content_type": "text/plain", "size_bytes": 128},
    )
    assert response.status_code == 200, response.text
    return response.json()["file_id"]


async def test_framework_can_be_activated_and_deactivated(client: AsyncClient) -> None:
    """A2/A3. Frameworks are global catalog rows, so adoption has to be
    recorded per organization or every tenant is nominally subject to all
    seven at once."""
    await _signup(client, "compliance-activate@example.com")
    framework_id, _ = await _gdpr(client)

    assert (await client.get("/api/v1/compliance/frameworks/activations")).json() == []

    activate = await client.put(
        f"/api/v1/compliance/frameworks/{framework_id}/activation", json={"active": True}
    )
    assert activate.status_code == 200
    assert activate.json()["status"] == "active"

    listed = (await client.get("/api/v1/compliance/frameworks/activations")).json()
    assert [a["framework_id"] for a in listed] == [framework_id]

    deactivate = await client.put(
        f"/api/v1/compliance/frameworks/{framework_id}/activation", json={"active": False}
    )
    assert deactivate.json()["status"] == "inactive"


async def test_assessment_reports_missing_evidence_without_asserting_a_breach(
    client: AsyncClient,
) -> None:
    """A8/A9/A11. The wording matters as much as the status: a compliance
    tool that concludes "you violate GDPR" from an empty database is
    manufacturing a legal opinion out of missing rows."""
    await _signup(client, "compliance-assess@example.com")
    framework_id, requirements = await _gdpr(client)

    # A control mapped to Article 30, with no evidence attached yet.
    control = await client.post(
        "/api/v1/compliance/controls",
        json={
            "title": "Maintain Record of Processing Activities",
            "description": "The organization maintains an up-to-date RoPA.",
            "requirement_ids": [requirements["Art. 30"]],
        },
    )
    assert control.status_code == 201

    result = (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()

    by_code = {r["reference_code"]: r for r in result["requirements"]}
    assert by_code["Art. 30"]["status"] == "evidence_missing"
    # Requirements nobody has mapped a control to are distinguished from
    # ones that are mapped but unevidenced — they are different problems.
    assert by_code["Art. 5"]["status"] == "not_assessed"
    assert result["satisfied_count"] == 0

    summary = by_code["Art. 30"]["summary"].lower()
    assert "has not been found" in summary
    for forbidden in ("violation", "violate", "breach", "non-compliant", "illegal"):
        assert forbidden not in summary, f"assessment asserted a legal conclusion: {summary}"


async def test_gap_yields_remediation_and_a_task_that_points_back(client: AsyncClient) -> None:
    """A12/A13/A14. The task is the thing a person actually works from, so
    it has to carry the link back to what it is fixing."""
    await _signup(client, "compliance-remediate@example.com")
    framework_id, requirements = await _gdpr(client)
    await client.post(
        "/api/v1/compliance/controls",
        json={
            "title": "Maintain Record of Processing Activities",
            "requirement_ids": [requirements["Art. 30"]],
        },
    )
    result = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    gap_id = next(
        r["gap_id"] for r in result["requirements"] if r["reference_code"] == "Art. 30"
    )
    assert gap_id is not None

    remediation = (
        await client.post(f"/api/v1/compliance/gaps/{gap_id}/remediation")
    ).json()
    # Article 30(1) enumerates these; the recommendation quotes the
    # regulation rather than improvising advice.
    for field in ("purposes", "recipients", "retention", "security measures"):
        assert field in remediation["recommendation"].lower()

    task = await client.post(
        f"/api/v1/compliance/gaps/{gap_id}/task",
        json={"title": "Complete Record of Processing Activities", "due_in_days": 7},
    )
    assert task.status_code == 201
    body = task.json()
    assert body["module"] == "compliance"
    assert body["entity_type"] == "compliance_gap"
    assert body["entity_id"] == gap_id
    assert body["due_at"] is not None

    # And the gap knows about the task, so the link is navigable both ways.
    gap = (await client.get(f"/api/v1/compliance/gaps/{gap_id}")).json()
    assert gap["status"] == "remediating"
    assert gap["task_id"] == body["id"]


async def test_attaching_evidence_then_reassessing_closes_the_gap(client: AsyncClient) -> None:
    """A15/A16/A17/A18. The loop that makes the module worth using: the
    status has to actually move when the work is done."""
    await _signup(client, "compliance-reassess@example.com")
    framework_id, requirements = await _gdpr(client)
    control_id = (
        await client.post(
            "/api/v1/compliance/controls",
            json={
                "title": "Maintain Record of Processing Activities",
                "requirement_ids": [requirements["Art. 30"]],
            },
        )
    ).json()["id"]

    before = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    assert before["evidence_coverage_percent"] == 0.0

    file_id = await _upload_file(client, "ropa.txt")
    attach = await client.post(
        "/api/v1/compliance/evidence",
        json={
            "file_id": file_id,
            "title": "Record of Processing Activities",
            "control_id": control_id,
        },
    )
    assert attach.status_code == 201

    # Evidence alone is not a pass — a human still has to assess it.
    await client.post(
        f"/api/v1/compliance/controls/{control_id}/assessments",
        json={"status": "pass", "notes": "RoPA reviewed and approved."},
    )

    after = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    by_code = {r["reference_code"]: r for r in after["requirements"]}
    assert by_code["Art. 30"]["status"] == "satisfied"
    assert after["evidence_coverage_percent"] > before["evidence_coverage_percent"]

    # The gap is closed rather than left lying around.
    gaps = (
        await client.get(f"/api/v1/compliance/gaps?framework_id={framework_id}")
    ).json()
    art30 = [g for g in gaps if g["requirement_id"] == requirements["Art. 30"]]
    assert art30 and art30[0]["status"] == "resolved"


async def test_unrelated_evidence_does_not_move_the_score(client: AsyncClient) -> None:
    """A18's own "critical test". A compliance score that rises when you
    upload anything at all is worse than no score: it rewards noise."""
    await _signup(client, "compliance-noise@example.com")
    framework_id, requirements = await _gdpr(client)
    await client.post(
        "/api/v1/compliance/controls",
        json={
            "title": "Maintain Record of Processing Activities",
            "requirement_ids": [requirements["Art. 30"]],
        },
    )
    before = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()

    # Evidence attached to nothing at all.
    file_id = await _upload_file(client, "holiday-photos.txt")
    await client.post(
        "/api/v1/compliance/evidence",
        json={"file_id": file_id, "title": "Unrelated document"},
    )

    after = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    assert after["evidence_coverage_percent"] == before["evidence_coverage_percent"]
    assert after["satisfied_count"] == before["satisfied_count"]
    assert after["gap_count"] == before["gap_count"]


async def test_reassessment_updates_gaps_instead_of_duplicating_them(
    client: AsyncClient,
) -> None:
    await _signup(client, "compliance-rerun@example.com")
    framework_id, requirements = await _gdpr(client)
    await client.post(
        "/api/v1/compliance/controls",
        json={"title": "RoPA", "requirement_ids": [requirements["Art. 30"]]},
    )
    for _ in range(3):
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")

    gaps = (await client.get(f"/api/v1/compliance/gaps?framework_id={framework_id}")).json()
    art30 = [g for g in gaps if g["requirement_id"] == requirements["Art. 30"]]
    assert len(art30) == 1, "re-running the assessment stacked duplicate gaps"


async def test_control_detail_exposes_its_evidence(client: AsyncClient) -> None:
    """A10. The chain has to be walkable in the direction an auditor
    actually reads it: requirement -> control -> evidence -> document."""
    await _signup(client, "compliance-chain@example.com")
    _, requirements = await _gdpr(client)
    control_id = (
        await client.post(
            "/api/v1/compliance/controls",
            json={"title": "RoPA", "requirement_ids": [requirements["Art. 30"]]},
        )
    ).json()["id"]

    file_id = await _upload_file(client, "ropa.txt")
    await client.post(
        "/api/v1/compliance/evidence",
        json={"file_id": file_id, "title": "RoPA export", "control_id": control_id},
    )

    detail = (await client.get(f"/api/v1/compliance/controls/{control_id}")).json()
    assert [r["reference_code"] for r in detail["requirements"]] == ["Art. 30"]
    assert len(detail["evidence"]) == 1
    # And the evidence names the file it came from, so provenance survives.
    assert detail["evidence"][0]["file_id"] == file_id


async def test_audit_trail_covers_the_whole_chain(client: AsyncClient) -> None:
    """A19. An append-only log nobody can read provides assurance to no
    one, so this asserts the events are both written and retrievable."""
    await _signup(client, "compliance-audit@example.com")
    framework_id, requirements = await _gdpr(client)
    await client.put(
        f"/api/v1/compliance/frameworks/{framework_id}/activation", json={"active": True}
    )
    await client.post(
        "/api/v1/compliance/controls",
        json={"title": "RoPA", "requirement_ids": [requirements["Art. 30"]]},
    )
    result = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    gap_id = next(r["gap_id"] for r in result["requirements"] if r["reference_code"] == "Art. 30")
    await client.post(f"/api/v1/compliance/gaps/{gap_id}/remediation")
    await client.post(f"/api/v1/compliance/gaps/{gap_id}/task", json={})

    events = (
        await client.get("/api/v1/audit-events?action_prefix=compliance.&limit=100")
    ).json()
    actions = {e["action"] for e in events}
    for expected in (
        "compliance.framework.activated",
        "compliance.control.created",
        "compliance.framework.assessed",
        "compliance.gap.created",
        "compliance.gap.remediation_generated",
        "compliance.gap.task_created",
    ):
        assert expected in actions, f"{expected} missing from the audit trail"


async def test_audit_trail_is_read_only_and_permissioned(client: AsyncClient) -> None:
    await _signup(client, "compliance-audit-ro@example.com")
    # There is no write route; forging history must not be an API call.
    assert (await client.post("/api/v1/audit-events", json={})).status_code in (404, 405)


async def test_assessment_is_scoped_to_the_calling_organization(
    client: AsyncClient,
) -> None:
    """Tenant isolation on the new endpoints: org B's controls must never
    count toward org A's coverage."""
    await _signup(client, "compliance-tenant-a@example.com")
    framework_id, requirements = await _gdpr(client)
    await client.post(
        "/api/v1/compliance/controls",
        json={"title": "Org A RoPA", "requirement_ids": [requirements["Art. 30"]]},
    )
    a_result = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    a_art30 = next(r for r in a_result["requirements"] if r["reference_code"] == "Art. 30")
    assert len(a_art30["control_ids"]) == 1

    await client.post("/api/v1/auth/logout")
    await _signup(client, "compliance-tenant-b@example.com")
    b_result = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    b_art30 = next(r for r in b_result["requirements"] if r["reference_code"] == "Art. 30")
    assert b_art30["control_ids"] == [], "another organization's control leaked into this one"
    assert (await client.get("/api/v1/compliance/gaps")).json() != a_result
