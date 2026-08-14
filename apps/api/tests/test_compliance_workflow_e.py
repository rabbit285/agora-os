"""Vendor due diligence, end to end.

Vendor -> Documents -> Questionnaire -> Privacy + Security review -> Risk
-> DPA -> Approval decision -> Vendor inventory.

The decision states carry most of the weight. A review process offering
only approve/reject forces the reviewer to either block a vendor the
business needs or wave through the caveat they were worried about, and
the second happens far more often — which is how a due diligence process
quietly becomes a rubber stamp.
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
            "full_name": "Vendor Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _vendor(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/compliance/vendors",
        json={
            "name": "NovaAI Cloud Ltd.",
            "description": "Hosted generative AI API (synthetic test vendor)",
            "category": "ai_service_provider",
            "risk_tier": "high",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _questionnaire_with_gaps(client: AsyncClient, vendor_id: str) -> str:
    """E4/E5: a questionnaire whose transfer and retention questions are
    deliberately left unanswered, so the reviews have something real to
    detect."""
    questionnaire_id = (
        await client.post(
            "/api/v1/compliance/questionnaires",
            json={"title": "NovaAI security questionnaire", "vendor_id": vendor_id},
        )
    ).json()["id"]

    for text in (
        "Do you encrypt customer data at rest and in transit?",
        "What is your international transfer mechanism for EU personal data?",
        "Confirm your AI retention policy: how long is prompt data retained?",
        "List your subprocessors.",
    ):
        response = await client.post(
            f"/api/v1/compliance/questionnaires/{questionnaire_id}/questions",
            json={"text": text},
        )
        assert response.status_code == 201, response.text
    return questionnaire_id


async def test_new_vendor_has_not_been_approved(client: AsyncClient) -> None:
    await _signup(client, "vendor-new@example.com")
    vendor_id = await _vendor(client)
    body = (await client.get(f"/api/v1/compliance/vendors/{vendor_id}")).json()
    assert body["approval_state"] == "not_submitted"
    assert body["approval_conditions"] is None


async def test_privacy_review_detects_the_missing_dpa_and_unanswered_questions(
    client: AsyncClient,
) -> None:
    """E6. The review reads the file: no DPA, and the transfer and
    retention questions nobody answered."""
    await _signup(client, "vendor-privacy@example.com")
    vendor_id = await _vendor(client)
    await _questionnaire_with_gaps(client, vendor_id)

    response = await client.post(f"/api/v1/compliance/vendors/{vendor_id}/privacy-review")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["assessment_type"] == "privacy"

    checks = {c["check"]: c for c in body["findings"]["checks"]}
    assert checks["Data processing agreement"]["outcome"] == "missing"
    assert checks["International transfer basis"]["outcome"] == "unanswered"
    assert checks["Retention and deletion"]["outcome"] == "unanswered"
    assert body["risk_conclusion"] == "high"


async def test_privacy_review_clears_once_the_dpa_is_signed(client: AsyncClient) -> None:
    """The review has to actually move when the work is done, or nobody
    will trust it enough to do the work."""
    await _signup(client, "vendor-dpa@example.com")
    vendor_id = await _vendor(client)

    before = (
        await client.post(f"/api/v1/compliance/vendors/{vendor_id}/privacy-review")
    ).json()
    assert {c["check"]: c["outcome"] for c in before["findings"]["checks"]}[
        "Data processing agreement"
    ] == "missing"

    await client.patch(
        f"/api/v1/compliance/vendors/{vendor_id}/dpa-status", json={"dpa_status": "signed"}
    )
    after = (await client.post(f"/api/v1/compliance/vendors/{vendor_id}/privacy-review")).json()
    assert {c["check"]: c["outcome"] for c in after["findings"]["checks"]}[
        "Data processing agreement"
    ] == "satisfied"


async def test_security_review_reports_absent_evidence(client: AsyncClient) -> None:
    """E7. A vendor with no documents on file has nothing supporting its
    answers, and the review says so rather than passing it."""
    await _signup(client, "vendor-security@example.com")
    vendor_id = await _vendor(client)
    await _questionnaire_with_gaps(client, vendor_id)

    body = (
        await client.post(f"/api/v1/compliance/vendors/{vendor_id}/security-review")
    ).json()
    assert body["assessment_type"] == "security"
    checks = {c["check"]: c for c in body["findings"]["checks"]}
    assert checks["Supporting evidence"]["outcome"] == "missing"
    assert "0 of 4" in checks["Questionnaire completion"]["detail"]


async def test_privacy_and_security_reviews_are_separate_records(
    client: AsyncClient,
) -> None:
    """They reach different conclusions about the same vendor; neither
    stands in for the other."""
    await _signup(client, "vendor-both@example.com")
    vendor_id = await _vendor(client)
    await client.post(f"/api/v1/compliance/vendors/{vendor_id}/privacy-review")
    await client.post(f"/api/v1/compliance/vendors/{vendor_id}/security-review")

    detail = (await client.get(f"/api/v1/compliance/vendors/{vendor_id}")).json()
    types = {a["assessment_type"] for a in detail["assessments"]}
    assert {"privacy", "security"} <= types


async def test_conditional_approval_requires_its_conditions(client: AsyncClient) -> None:
    """E11, and the reason the state is worth having. A vendor marked
    "conditionally approved" with nobody able to say what the condition
    was is the record that makes the whole state meaningless later."""
    await _signup(client, "vendor-conditional@example.com")
    vendor_id = await _vendor(client)

    refused = await client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/approval",
        json={"decision": "conditionally_approved"},
    )
    assert refused.status_code == 422
    assert "conditions" in refused.json()["error"]["message"].lower()

    accepted = await client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/approval",
        json={
            "decision": "conditionally_approved",
            "conditions": "Test and non-sensitive data only until transfer evidence is verified.",
        },
    )
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["approval_state"] == "conditionally_approved"
    assert "non-sensitive" in body["approval_conditions"]
    assert body["approval_decided_at"] is not None


async def test_a_conditionally_approved_vendor_is_not_fully_approved(
    client: AsyncClient,
) -> None:
    """E12. The inventory must not round a conditional decision up."""
    await _signup(client, "vendor-inventory@example.com")
    vendor_id = await _vendor(client)
    await client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/approval",
        json={"decision": "conditionally_approved", "conditions": "Limited to test data."},
    )

    listed = (await client.get("/api/v1/compliance/vendors")).json()
    vendor = next(v for v in listed if v["id"] == vendor_id)
    assert vendor["approval_state"] == "conditionally_approved"
    assert vendor["approval_state"] != "approved"


async def test_full_approval_clears_stale_conditions(client: AsyncClient) -> None:
    """Conditions that no longer apply must not linger on an approved
    vendor and be mistaken for live restrictions."""
    await _signup(client, "vendor-clears@example.com")
    vendor_id = await _vendor(client)
    await client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/approval",
        json={"decision": "conditionally_approved", "conditions": "Test data only."},
    )
    approved = await client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/approval", json={"decision": "approved"}
    )
    assert approved.json()["approval_state"] == "approved"
    assert approved.json()["approval_conditions"] is None


async def test_questionnaire_cannot_be_attached_to_another_tenants_vendor(
    client: AsyncClient,
) -> None:
    await _signup(client, "vendor-iso-a@example.com")
    vendor_id = await _vendor(client)
    await client.post("/api/v1/auth/logout")

    await _signup(client, "vendor-iso-b@example.com")
    response = await client.post(
        "/api/v1/compliance/questionnaires",
        json={"title": "Sneaky", "vendor_id": vendor_id},
    )
    assert response.status_code == 404


async def test_reviews_and_decision_are_audited(client: AsyncClient) -> None:
    await _signup(client, "vendor-audit@example.com")
    vendor_id = await _vendor(client)
    await client.post(f"/api/v1/compliance/vendors/{vendor_id}/privacy-review")
    await client.post(f"/api/v1/compliance/vendors/{vendor_id}/security-review")
    await client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/approval",
        json={"decision": "conditionally_approved", "conditions": "Test data only."},
    )

    events = (
        await client.get("/api/v1/audit-events?action_prefix=compliance.vendor&limit=50")
    ).json()
    actions = {e["action"] for e in events}
    for expected in (
        "compliance.vendor.privacy_reviewed",
        "compliance.vendor.security_reviewed",
        "compliance.vendor.approval_decided",
    ):
        assert expected in actions, f"{expected} missing from the audit trail"


async def test_review_states_it_is_not_an_independent_audit(client: AsyncClient) -> None:
    """A green review is the moment someone stops looking, so it says
    plainly what it was based on."""
    await _signup(client, "vendor-coverage@example.com")
    vendor_id = await _vendor(client)
    body = (await client.post(f"/api/v1/compliance/vendors/{vendor_id}/privacy-review")).json()
    assert "not an independent audit" in body["findings"]["coverage_note"]
