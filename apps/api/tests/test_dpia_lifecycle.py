"""The DPIA lifecycle, end to end: screening → draft → … → completed.

The workflow had the right pieces and no spine holding them together. A
status dropdown could move a DPIA from `screening` straight to
`approved`, skipping the decision the screening exists to capture.
"Review" was inferred from whether the text still began with Veyntra's
draft marker, so deleting one word counted as having read it. Suggested
risks were recomputed on every request and never stored, so there was
nothing to approve or dismiss. Nothing was ever *completed*, and nothing
noticed when the processing underneath an assessment moved on.

These pin the replacement. The through-line in all of them: Veyntra
prepares, and every claim on the record traces to somebody who made it.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import dpia_workflow
from app.compliance.models import DPIA, DpiaRiskSuggestion, Risk, Vendor


async def _screened(client: AsyncClient, email: str) -> dict:
    """An organization, an AI system, its ROPA entry, and a screened DPIA."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )
    await client.post(
        "/api/v1/compliance/vendors",
        json={"name": "OpenAI", "category": "ai", "country": "US"},
    )
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "AI Customer Support",
            "vendor": "OpenAI",
            "purpose": "Answering customer product questions in the support inbox.",
            "affected_users": ["Customers"],
            "processed_data": [
                {"name": "Contact information", "classification": "confidential"},
                {"name": "Support conversation content", "classification": "confidential"},
            ],
        },
    )
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    suggestions = (await client.get("/api/v1/compliance/privacy/suggestions")).json()
    accepted = (
        await client.post(
            f"/api/v1/compliance/privacy/suggestions/{suggestions[0]['id']}/accept",
            json={
                "legal_basis": "contract",
                "retention_period": "24 months",
                "special_category": True,
                "special_category_condition": "explicit_consent",
            },
        )
    ).json()
    workflow = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": accepted["created_record_id"]},
        )
    ).json()
    workflow["activity_id"] = accepted["created_record_id"]
    return workflow


async def _confirmed(client: AsyncClient, email: str) -> dict:
    """…and a person confirming a DPIA is required."""
    screened = await _screened(client, email)
    workflow = (
        await client.post(
            f"/api/v1/compliance/dpias/{screened['id']}/screening/decision",
            json={"decision": "required"},
        )
    ).json()
    workflow["activity_id"] = screened["activity_id"]
    return workflow


# --- §1/§26: one lifecycle, and the dropdown cannot skip a decision -----


@pytest.mark.asyncio
async def test_a_screening_dpia_cannot_be_moved_by_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§1: the way out of screening is to decide it.

    A status field that accepts anything makes the screening decorative:
    somebody could mark a DPIA approved without ever recording whether
    an assessment was required, which is the one thing the screening
    exists to capture.
    """
    screened = await _screened(client, "lifecycle1@example.com")
    assert screened["status"] == "screening"

    response = await client.patch(
        f"/api/v1/compliance/dpias/{screened['id']}/status",
        json={"status": "approved"},
    )
    assert response.status_code == 422, response.text
    assert "screening decision" in response.json()["error"]["message"]

    # And the record did not move.
    current = (await client.get(f"/api/v1/compliance/dpias/{screened['id']}")).json()
    assert current["status"] == "screening"


@pytest.mark.asyncio
async def test_the_lifecycle_only_offers_reachable_states(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§26: the UI is told what is possible rather than guessing."""
    screened = await _screened(client, "lifecycle2@example.com")
    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{screened['id']}/workflow")
    ).json()
    assert workflow["allowed_transitions"] == []

    confirmed = (
        await client.post(
            f"/api/v1/compliance/dpias/{screened['id']}/screening/decision",
            json={"decision": "required"},
        )
    ).json()
    assert confirmed["status"] == "draft"
    assert confirmed["allowed_transitions"] == ["in_review", "rejected"]


@pytest.mark.asyncio
async def test_the_status_field_cannot_complete_a_dpia(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§22: completion is the check, not a word in a dropdown.

    Completing freezes the snapshot of what was concluded. A status
    field that could reach "completed" on its own would produce a
    finished DPIA with no record of what it finished.
    """
    confirmed = await _confirmed(client, "lifecycle22@example.com")
    dpia_id = confirmed["id"]
    await client.patch(
        f"/api/v1/compliance/dpias/{dpia_id}/status", json={"status": "in_review"}
    )
    approved = await client.patch(
        f"/api/v1/compliance/dpias/{dpia_id}/status", json={"status": "approved"}
    )
    assert approved.status_code == 200, approved.text

    response = await client.patch(
        f"/api/v1/compliance/dpias/{dpia_id}/status", json={"status": "completed"}
    )
    assert response.status_code == 422
    assert "completion check" in response.json()["error"]["message"]

    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert workflow["status"] == "approved"
    assert workflow["snapshot"] is None
    assert "completed" not in workflow["allowed_transitions"]


# --- §5/§28: declining produces a record, not an assessment -------------


@pytest.mark.asyncio
async def test_deciding_no_dpia_is_needed_does_not_leave_an_assessment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§28: "not required" is a conclusion, not an approved assessment.

    It used to be stored as `approved`, which reads on every list as
    though the DPIA had been carried out and signed off — the opposite
    of what was decided.
    """
    screened = await _screened(client, "lifecycle3@example.com")
    response = await client.post(
        f"/api/v1/compliance/dpias/{screened['id']}/screening/decision",
        json={
            "decision": "not_required",
            "rationale": "No systematic monitoring; the support inbox is reactive.",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "not_required"
    assert body["screening_decision"] == "not_required"
    assert body["screening_decision_rationale"].startswith("No systematic monitoring")
    # No assessment was produced.
    assert body["processing_description"] is None
    assert body["necessity_assessment"] is None
    # And nothing is outstanding: the screening is the record.
    assert body["completion_blockers"] == []
    # Nor is there a risk register to review.
    assert body["suggested_risks"] == []


@pytest.mark.asyncio
async def test_declining_still_needs_a_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    screened = await _screened(client, "lifecycle4@example.com")
    response = await client.post(
        f"/api/v1/compliance/dpias/{screened['id']}/screening/decision",
        json={"decision": "not_required"},
    )
    assert response.status_code == 422
    assert "needs a reason" in response.json()["error"]["message"]


# --- §13/§31: suggestions are records a person can act on ---------------


@pytest.mark.asyncio
async def test_screening_persists_the_risks_it_proposes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§13: proposals exist between two page loads.

    They used to be recomputed on every read and never stored, so there
    was nothing to approve, nothing to dismiss, and no way to stop one
    reappearing after somebody decided it was not a real risk.
    """
    confirmed = await _confirmed(client, "lifecycle5@example.com")
    suggested = confirmed["suggested_risks"]
    assert len(suggested) >= 3
    assert all(row["id"] for row in suggested)
    assert all(row["status"] == "suggested" for row in suggested)
    # Each carries the fact it was read from.
    assert all(row["reason"] for row in suggested)
    # And never a rating: that is the judgement the review exists to make.
    assert all("likelihood" not in row for row in suggested)


@pytest.mark.asyncio
async def test_rescreening_does_not_duplicate_or_revive_suggestions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§31: repeated screening is idempotent, in both directions."""
    confirmed = await _confirmed(client, "lifecycle6@example.com")
    first = confirmed["suggested_risks"]
    dismissed_id = first[0]["id"]

    await client.post(
        f"/api/v1/compliance/dpias/{confirmed['id']}/risk-suggestions/{dismissed_id}/dismiss",
        json={"reason": "The support inbox does not surface model output to customers."},
    )

    # Screen the same activity again — the ordinary way somebody would.
    again = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": confirmed["activity_id"]},
        )
    ).json()
    assert again["reused_existing"] is True
    assert again["id"] == confirmed["id"]

    rows = list(
        (
            await db_session.execute(
                select(DpiaRiskSuggestion).where(
                    DpiaRiskSuggestion.dpia_id == uuid.UUID(confirmed["id"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == len(first), "re-screening duplicated the proposals"
    dismissed = [row for row in rows if str(row.id) == dismissed_id][0]
    assert dismissed.status == "dismissed", "a dismissed risk came back"


@pytest.mark.asyncio
async def test_dismissing_a_suggestion_needs_a_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    confirmed = await _confirmed(client, "lifecycle7@example.com")
    suggestion_id = confirmed["suggested_risks"][0]["id"]
    response = await client.post(
        f"/api/v1/compliance/dpias/{confirmed['id']}/risk-suggestions/{suggestion_id}/dismiss",
        json={"reason": "   "},
    )
    assert response.status_code == 422


# --- §14/§29: no rating before somebody rates something -----------------


@pytest.mark.asyncio
async def test_approving_a_suggestion_is_what_creates_the_risk(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§29: before approval there is no inherent risk; after, there is."""
    confirmed = await _confirmed(client, "lifecycle8@example.com")
    assert confirmed["inherent_risk"] is None
    assert confirmed["residual_risk"] is None
    assert confirmed["can_calculate_residual"] is False

    suggestion_id = confirmed["suggested_risks"][0]["id"]
    after = (
        await client.post(
            f"/api/v1/compliance/dpias/{confirmed['id']}/risk-suggestions/{suggestion_id}/approve",
            json={
                "likelihood": "medium",
                "impact": "high",
                "affected_data_subjects": "Customers contacting support",
            },
        )
    ).json()

    assert after["risk_count"] == 1
    assert after["assessed_count"] == 1
    # medium × high is the rating a person supplied, not a default.
    assert after["inherent_risk"] == "high"
    # Nothing has been mitigated, so there is still no residual figure.
    assert after["residual_risk"] is None
    assert after["can_calculate_residual"] is False

    risk = (
        await db_session.execute(select(Risk).where(Risk.dpia_id == uuid.UUID(confirmed["id"])))
    ).scalars().one()
    assert risk.affected_data_subjects == "Customers contacting support"
    assert risk.category == "privacy"


@pytest.mark.asyncio
async def test_a_suggestion_cannot_be_decided_twice(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§31: a double-submit is one decision, not two risks."""
    confirmed = await _confirmed(client, "lifecycle9@example.com")
    suggestion_id = confirmed["suggested_risks"][0]["id"]
    body = {"likelihood": "low", "impact": "low"}
    first = await client.post(
        f"/api/v1/compliance/dpias/{confirmed['id']}/risk-suggestions/{suggestion_id}/approve",
        json=body,
    )
    assert first.status_code == 200
    second = await client.post(
        f"/api/v1/compliance/dpias/{confirmed['id']}/risk-suggestions/{suggestion_id}/approve",
        json=body,
    )
    assert second.status_code == 422
    assert "already approved" in second.json()["error"]["message"]

    risks = list(
        (
            await db_session.execute(select(Risk).where(Risk.dpia_id == uuid.UUID(confirmed["id"])))
        )
        .scalars()
        .all()
    )
    assert len(risks) == 1


# --- §8: review is recorded, not inferred from the wording --------------


@pytest.mark.asyncio
async def test_a_section_is_reviewed_when_somebody_says_so(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8: agreeing with a draft is a decision, not an edit.

    Completion used to test whether the text still began with Veyntra's
    draft marker, which meant a reviewer who agreed verbatim had to alter
    the words before the product believed them — and deleting one word
    counted as review.
    """
    confirmed = await _confirmed(client, "lifecycle10@example.com")
    dpia_id = confirmed["id"]
    codes = {b["code"] for b in confirmed["completion_blockers"]}
    assert "processing_description_unreviewed" in codes

    approved = (
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/sections/approve",
            json={"section": "processing_description"},
        )
    ).json()

    assert [row["section"] for row in approved["section_reviews"]] == [
        "processing_description"
    ]
    codes = {b["code"] for b in approved["completion_blockers"]}
    assert "processing_description_unreviewed" not in codes
    # The text is untouched — the reviewer agreed with it as drafted.
    assert approved["processing_description"] == confirmed["processing_description"]


@pytest.mark.asyncio
async def test_editing_a_section_withdraws_its_sign_off(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An approval is a statement about particular words.

    Keeping the tick after those words are rewritten would leave the
    record saying somebody approved text they never saw.
    """
    confirmed = await _confirmed(client, "lifecycle11@example.com")
    dpia_id = confirmed["id"]
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/sections/approve",
        json={"section": "necessity_assessment"},
    )
    # Substantive replacement text: the point here is that editing
    # withdraws the sign-off, not that short text is refused — which the
    # content gates cover separately.
    await client.patch(
        f"/api/v1/compliance/dpias/{dpia_id}/sections",
        json={
            "necessity_assessment": (
                "The DPO reviewed this and concluded the processing is "
                "necessary to deliver the contracted support service, and "
                "that handling enquiries without the customer's contact "
                "details would not achieve it."
            )
        },
    )
    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert workflow["section_reviews"] == []
    codes = {b["code"] for b in workflow["completion_blockers"]}
    assert "necessity_assessment_unreviewed" in codes


# --- §12: consultation is a fact, and Veyntra never drafts it -----------


@pytest.mark.asyncio
async def test_consultation_is_unresolved_until_somebody_answers(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12: "none performed" is an answer; null means nobody looked."""
    confirmed = await _confirmed(client, "lifecycle12@example.com")
    assert confirmed["consultation_performed"] is None
    assert confirmed["consultation_state"] == "not_decided"
    codes = {b["code"] for b in confirmed["completion_blockers"]}
    assert "consultation_not_recorded" in codes

    recorded = (
        await client.post(
            f"/api/v1/compliance/dpias/{confirmed['id']}/consultation",
            json={
                "performed": False,
                "notes": "No DPO is appointed and the processing is not high risk to date.",
            },
        )
    ).json()
    assert recorded["consultation_performed"] is False
    assert recorded["consultation_state"] == "no_consultation"
    codes = {b["code"] for b in recorded["completion_blockers"]}
    assert "consultation_not_recorded" not in codes


@pytest.mark.asyncio
async def test_recording_a_consultation_needs_who_was_consulted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    confirmed = await _confirmed(client, "lifecycle13@example.com")
    response = await client.post(
        f"/api/v1/compliance/dpias/{confirmed['id']}/consultation",
        json={"performed": True},
    )
    assert response.status_code == 422
    assert "who was consulted" in response.json()["error"]["message"]


# --- §16: mitigation is work somebody owns ------------------------------


@pytest.mark.asyncio
async def test_a_risk_can_open_remediation_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§16/§31: reuses the task system, and a double press is one task."""
    confirmed = await _confirmed(client, "lifecycle14@example.com")
    suggestion_id = confirmed["suggested_risks"][0]["id"]
    await client.post(
        f"/api/v1/compliance/dpias/{confirmed['id']}/risk-suggestions/{suggestion_id}/approve",
        json={"likelihood": "high", "impact": "high"},
    )
    risk = (
        await db_session.execute(select(Risk).where(Risk.dpia_id == uuid.UUID(confirmed["id"])))
    ).scalars().one()

    body = {
        "title": "Apply content minimisation before the model call",
        "description": "Strip attachments and redact identifiers in the support pipeline.",
        "priority": "high",
    }
    first = await client.post(f"/api/v1/compliance/risks/{risk.id}/remediation", json=body)
    assert first.status_code == 201, first.text
    second = await client.post(f"/api/v1/compliance/risks/{risk.id}/remediation", json=body)
    assert second.json()["id"] == first.json()["id"]

    await db_session.refresh(risk)
    # The commitment is on the risk that its residual rating will rest on.
    assert "content minimisation" in (risk.additional_mitigations or "")


# --- §22/§23: completion is a gate, and what it freezes -----------------


async def _ready_to_complete(client: AsyncClient, db_session: AsyncSession, email: str) -> dict:
    confirmed = await _confirmed(client, email)
    dpia_id = confirmed["id"]

    suggestions = confirmed["suggested_risks"]
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{suggestions[0]['id']}/approve",
        json={"likelihood": "low", "impact": "low"},
    )
    for row in suggestions[1:]:
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{row['id']}/dismiss",
            json={"reason": "Covered by the existing access-control programme."},
        )

    risk = (
        await db_session.execute(select(Risk).where(Risk.dpia_id == uuid.UUID(dpia_id)))
    ).scalars().one()
    await client.patch(
        f"/api/v1/compliance/risks/{risk.id}/residual",
        json={"residual_likelihood": "low", "residual_impact": "low"},
    )
    await client.post(f"/api/v1/compliance/dpias/{dpia_id}/recalculate-residual")

    for section in (
        "processing_description",
        "necessity_assessment",
        "proportionality_assessment",
    ):
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/sections/approve",
            json={"section": section},
        )
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/consultation",
        json={"performed": True, "party": "Zach Warren", "role": "DPO",
              "notes": "Reviewed with the DPO on the record."},
    )
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/sections/approve",
        json={"section": "consultation_notes"},
    )
    return (await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")).json()


@pytest.mark.asyncio
async def test_completion_refuses_and_says_everything_that_is_missing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§22: all of it at once, so the work can be finished in one pass."""
    confirmed = await _confirmed(client, "lifecycle15@example.com")
    response = await client.post(f"/api/v1/compliance/dpias/{confirmed['id']}/complete")
    assert response.status_code == 422
    detail = response.json()["error"]["message"]
    assert "consultation" in detail.lower()
    assert "suggested risk" in detail.lower()
    # Names the review, not a missing risk — a reviewer who concluded
    # there were none should not read this as "go and invent one".
    assert "risk assessment has not been reviewed" in detail


@pytest.mark.asyncio
async def test_a_completed_dpia_freezes_what_it_concluded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§23: the snapshot is the record, and it is written once."""
    ready = await _ready_to_complete(client, db_session, "lifecycle16@example.com")
    assert ready["can_complete"] is True, ready["completion_blockers"]

    completed = (
        await client.post(f"/api/v1/compliance/dpias/{ready['id']}/complete")
    ).json()
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None
    assert completed["completed_by_name"] == "Zach Warren"

    snapshot = completed["snapshot"]
    assert snapshot["processing"]["title"] == "AI Customer Support"
    assert snapshot["processing"]["vendors"] == [{"name": "OpenAI", "country": "US"}]
    assert snapshot["screening"]["decision"] == "required"
    assert snapshot["screening"]["decided_by"] == "Zach Warren"
    assert snapshot["consultation"]["party"] == "Zach Warren"
    assert len(snapshot["risks"]) == 1
    assert snapshot["risks"][0]["likelihood"] == "low"
    # Dismissals are part of what an assessment concluded: an auditor
    # asking why something is absent should find the answer here.
    assert len(snapshot["dismissed_risks"]) >= 1
    assert "access-control programme" in snapshot["dismissed_risks"][0]["reason"]


@pytest.mark.asyncio
async def test_a_completed_dpia_cannot_be_edited(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ready = await _ready_to_complete(client, db_session, "lifecycle17@example.com")
    await client.post(f"/api/v1/compliance/dpias/{ready['id']}/complete")

    edit = await client.patch(
        f"/api/v1/compliance/dpias/{ready['id']}/sections",
        json={"necessity_assessment": "Rewritten after the fact."},
    )
    assert edit.status_code == 422
    assert "frozen" in edit.json()["error"]["message"]

    move = await client.patch(
        f"/api/v1/compliance/dpias/{ready['id']}/status",
        json={"status": "draft"},
    )
    assert move.status_code == 422


# --- §18/§30: high residual risk cannot be signed off quietly -----------


@pytest.mark.asyncio
async def test_high_residual_risk_requires_an_approval_before_completion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§30: Article 36's case, enforced rather than described."""
    confirmed = await _confirmed(client, "lifecycle18@example.com")
    dpia_id = confirmed["id"]
    suggestions = confirmed["suggested_risks"]

    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{suggestions[0]['id']}/approve",
        json={"likelihood": "high", "impact": "high"},
    )
    for row in suggestions[1:]:
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{row['id']}/dismiss",
            json={"reason": "Not applicable to this processing."},
        )
    risk = (
        await db_session.execute(select(Risk).where(Risk.dpia_id == uuid.UUID(dpia_id)))
    ).scalars().one()
    await client.patch(
        f"/api/v1/compliance/risks/{risk.id}/residual",
        json={"residual_likelihood": "high", "residual_impact": "high"},
    )
    workflow = (
        await client.post(f"/api/v1/compliance/dpias/{dpia_id}/recalculate-residual")
    ).json()
    assert workflow["residual_risk_level"] == "high"
    # Raised from the rating itself, not from somebody later trying to
    # complete.
    assert workflow["approval_id"] is not None

    for section in dpia_workflow.SECTIONS:
        if section == "consultation_notes":
            await client.post(
                f"/api/v1/compliance/dpias/{dpia_id}/consultation",
                json={"performed": True, "party": "Zach Warren", "role": "DPO",
                      "notes": "Reviewed."},
            )
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/sections/approve",
            json={"section": section},
        )

    blocked = await client.post(f"/api/v1/compliance/dpias/{dpia_id}/complete")
    assert blocked.status_code == 422
    assert "Article 36" in blocked.json()["error"]["message"]


# --- §24: the ground moving does not rewrite the assessment -------------


@pytest.mark.asyncio
async def test_a_vendor_moving_country_flags_a_completed_dpia_without_editing_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§24: a recommendation to look again, never a silent update."""
    ready = await _ready_to_complete(client, db_session, "lifecycle19@example.com")
    completed = (
        await client.post(f"/api/v1/compliance/dpias/{ready['id']}/complete")
    ).json()
    frozen = completed["snapshot"]["processing"]["vendors"]
    assert frozen == [{"name": "OpenAI", "country": "US"}]

    # The processor moves. However the vendor record came to change,
    # the completed assessment was written against the old country.
    vendor = (
        await db_session.execute(select(Vendor).where(Vendor.name == "OpenAI"))
    ).scalars().one()
    vendor.country = "IN"
    await db_session.commit()

    after = (
        await client.get(f"/api/v1/compliance/dpias/{ready['id']}/workflow")
    ).json()
    assert after["review_reason"] is not None
    assert "OpenAI moved from US to IN" in after["review_reason"]
    # The completed record did not change.
    assert after["snapshot"]["processing"]["vendors"] == frozen
    assert after["status"] == "completed"

    # §31: reading the page again does not flag it a second time.
    flagged_at = after["review_flagged_at"]
    again = (
        await client.get(f"/api/v1/compliance/dpias/{ready['id']}/workflow")
    ).json()
    assert again["review_flagged_at"] == flagged_at


# --- §19: one queue, and it knows about all of this ---------------------


@pytest.mark.asyncio
async def test_the_review_center_carries_the_dpia_decisions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19: no second queue, and the screening item is open when it should be.

    The screening item used to filter on draft/in_review — the states a
    DPIA reaches *because* somebody decided — so it was invisible while
    the decision was outstanding and appeared afterwards asking for an
    answered question.
    """
    screened = await _screened(client, "lifecycle20@example.com")
    center = (await client.get("/api/v1/compliance/review-center")).json()
    privacy = [c for c in center["categories"] if c["key"] == "privacy_decisions"][0]
    kinds = {item["id"] for item in privacy["items"]}
    assert f"privacy-screening-{screened['id']}" in kinds

    await client.post(
        f"/api/v1/compliance/dpias/{screened['id']}/screening/decision",
        json={"decision": "required"},
    )
    center = (await client.get("/api/v1/compliance/review-center")).json()
    privacy = [c for c in center["categories"] if c["key"] == "privacy_decisions"][0]
    ids = {item["id"] for item in privacy["items"]}
    # Decided, so it closes…
    assert f"privacy-screening-{screened['id']}" not in ids
    # …and the assessment that opened takes its place, saying what is left.
    assert f"privacy-dpia-{screened['id']}" in ids
    item = [i for i in privacy["items"] if i["id"] == f"privacy-dpia-{screened['id']}"][0]
    assert "suggested risk" in item["detail"].lower()


# --- §25: the record we already have is repaired, not replaced ----------


@pytest.mark.asyncio
async def test_screening_an_activity_twice_continues_one_assessment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§25/§31: no duplicate DPIA, ever."""
    confirmed = await _confirmed(client, "lifecycle21@example.com")
    again = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": confirmed["activity_id"]},
        )
    ).json()
    assert again["id"] == confirmed["id"]
    # Re-screening a confirmed DPIA does not send it back to screening.
    assert again["status"] == "draft"

    rows = list(
        (await db_session.execute(select(DPIA))).scalars().all()
    )
    assert len([row for row in rows if str(row.id) == confirmed["id"]]) == 1
