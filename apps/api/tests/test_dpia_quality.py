"""Content quality, as distinct from workflow completeness.

The lifecycle was right and the content was not. Veyntra drafted
*instructions* — "State why this processing is necessary", "Assess
whether the data collected is limited" — a reviewer pressed Approve, and
the DPIA completed carrying guidance where its argument belonged. A risk
conclusion passed on the rationale "ok". A medical-leave assessment
completed while reporting "no personal-data categories are recorded".

Every test here pins the same rule: **absent information must not become
a positive conclusion.** No categories recorded is not "nothing
sensitive". No risks entered is not "no material risk". An unedited
prompt is not an assessment somebody made.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance import dpia_completion, dpia_quality, dpia_workflow
from app.compliance.models import DPIA, ProcessingActivity

# A rationale that actually engages with the processing — the shape §21
# asks for.
STRONG_RATIONALE = (
    "The processing is limited to absence dates needed to administer leave, "
    "access is restricted to the two HR administrators who action requests, "
    "records are retained for six years and then deleted, no automated "
    "decisions are made about employees, and no data reaches a processor "
    "outside the organization, so the remaining impact on individuals is "
    "minimal."
)


def _refused(response) -> str:
    return response.json()["error"]["message"]


async def _dpia_for(
    client: AsyncClient,
    email: str,
    *,
    name: str,
    purpose: str,
    categories: list[str] | None = None,
    retention: str | None = "6 years after employment ends",
    subjects: str = "Employees",
) -> dict:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )
    body: dict = {
        "name": name,
        "purpose": purpose,
        "legal_basis": "legal_obligation",
        "data_subjects": subjects,
        "data_categories": categories or [],
    }
    if retention:
        body["retention_period"] = retention
    activity = (
        await client.post("/api/v1/compliance/processing-activities", json=body)
    ).json()
    screened = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity["id"]},
        )
    ).json()
    workflow = (
        await client.post(
            f"/api/v1/compliance/dpias/{screened['id']}/screening/decision",
            json={"decision": "required"},
        )
    ).json()
    workflow["activity_id"] = activity["id"]
    return workflow


# --- §1/§17: guidance is not an assessment ------------------------------


def test_instructional_text_is_recognised_as_guidance() -> None:
    """§17: the exact sentences that used to pass as assessments."""
    assert dpia_quality.is_instructional(
        "State why this processing is necessary to achieve it, and what less "
        "intrusive alternative was considered and rejected."
    )
    assert dpia_quality.is_instructional(
        "Assess whether the data collected is limited to what the purpose "
        "requires, and whether the retention period is the shortest that "
        "serves it."
    )
    assert dpia_quality.is_instructional(
        "[Veyntra draft — review required] Needs human input. Record whether "
        "the DPO was consulted."
    )
    # A finding is not guidance, however long or short.
    assert not dpia_quality.is_instructional(
        "The processing collects absence dates and fit notes, which is the "
        "data the recorded purpose operates on."
    )


def test_a_section_holding_guidance_cannot_be_approved() -> None:
    problem = dpia_quality.section_problem(
        "necessity_assessment",
        "[Veyntra draft — review required] The recorded purpose is: Administer "
        "leave. State why this processing is necessary to achieve it.",
    )
    assert problem is not None
    assert "guidance, not a completed assessment" in problem


@pytest.mark.asyncio
async def test_approval_refuses_guidance_over_the_api(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: Approve is refused, and says why."""
    workflow = await _dpia_for(
        client,
        "quality1@example.com",
        name="Employee leave administration",
        purpose="Administer statutory and contractual employee leave",
        categories=["Absence dates"],
    )
    dpia_id = workflow["id"]

    dpia = await db_session.get(DPIA, uuid.UUID(dpia_id))
    dpia.necessity_assessment = (
        "[Veyntra draft — review required] State why this processing is "
        "necessary to achieve it, and what less intrusive alternative was "
        "considered and rejected."
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/sections/approve",
        json={"section": "necessity_assessment"},
    )
    assert response.status_code == 422
    assert "guidance, not a completed assessment" in _refused(response)


# --- §3/§4/§18: what Veyntra now drafts ---------------------------------


@pytest.mark.asyncio
async def test_the_drafts_are_assessments_and_can_be_approved(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3/§4/§18: the draft is the analysis, not the question."""
    workflow = await _dpia_for(
        client,
        "quality2@example.com",
        name="Employee leave administration",
        purpose="Administer statutory and contractual employee leave obligations",
        categories=["Absence dates", "Leave entitlement"],
    )

    necessity = workflow["necessity_assessment"]
    proportionality = workflow["proportionality_assessment"]

    # No instruction anywhere in them.
    assert not dpia_quality.is_instructional(necessity)
    assert not dpia_quality.is_instructional(proportionality)
    assert dpia_quality.section_problem("necessity_assessment", necessity) is None
    assert (
        dpia_quality.section_problem("proportionality_assessment", proportionality)
        is None
    )

    # And they argue from the recorded facts.
    assert "necessary to administer" in necessity
    assert "less intrusive" not in necessity.lower() or "considered" in necessity
    assert "absence dates" in proportionality.lower()
    assert "6 years" in proportionality

    for section in ("necessity_assessment", "proportionality_assessment"):
        approved = await client.post(
            f"/api/v1/compliance/dpias/{workflow['id']}/sections/approve",
            json={"section": section},
        )
        assert approved.status_code == 200, approved.text


@pytest.mark.asyncio
async def test_consultation_is_left_empty_rather_than_prompted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A prompt in the field is the thing a reviewer ends up approving."""
    workflow = await _dpia_for(
        client,
        "quality3@example.com",
        name="Employee leave administration",
        purpose="Administer employee leave",
        categories=["Absence dates"],
    )
    assert workflow["consultation_notes"] is None


# --- §5/§7/§19: missing facts are not a clean bill of health ------------


@pytest.mark.asyncio
async def test_missing_data_categories_block_completion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19: an assessment that cannot say what data it covered."""
    workflow = await _dpia_for(
        client,
        "quality4@example.com",
        name="Employee medical-leave administration",
        purpose="Administer statutory and contractual medical leave",
        categories=[],
    )
    fresh = (
        await client.get(f"/api/v1/compliance/dpias/{workflow['id']}/workflow")
    ).json()

    codes = {gap["code"] for gap in fresh["missing_facts"]}
    assert "missing_data_categories" in codes
    # §14: each item deep-links to where it is fixed.
    assert all(gap["href"] for gap in fresh["missing_facts"])

    blockers = {b["code"] for b in fresh["completion_blockers"]}
    assert "missing_data_categories" in blockers


# --- §6/§19: the medical-leave case -------------------------------------


@pytest.mark.asyncio
async def test_medical_leave_raises_a_special_category_question(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: never "no categories recorded" and carry on."""
    workflow = await _dpia_for(
        client,
        "quality5@example.com",
        name="Employee medical-leave administration",
        purpose="Administer statutory and contractual medical leave obligations",
        categories=[],
    )
    fresh = (
        await client.get(f"/api/v1/compliance/dpias/{workflow['id']}/workflow")
    ).json()

    kinds = {signal["kind"] for signal in fresh["special_category_signals"]}
    assert "health or medical information" in kinds
    # The detection is checkable rather than taken on trust.
    assert all(signal["evidence"] for signal in fresh["special_category_signals"])
    assert fresh["special_category_confirmed"] is None

    blockers = {b["code"] for b in fresh["completion_blockers"]}
    assert "special_category_unconfirmed" in blockers


@pytest.mark.asyncio
async def test_ruling_out_special_category_data_needs_a_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow = await _dpia_for(
        client,
        "quality6@example.com",
        name="Employee medical-leave administration",
        purpose="Administer medical leave",
        categories=[],
    )
    dpia_id = workflow["id"]

    refused = await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/special-category",
        json={"confirmed": False},
    )
    assert refused.status_code == 422
    assert "needs a reason" in _refused(refused)

    resolved = (
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/special-category",
            json={
                "confirmed": True,
                "rationale": "Fit notes are held for statutory sick pay.",
            },
        )
    ).json()
    assert resolved["special_category_confirmed"] is True
    blockers = {b["code"] for b in resolved["completion_blockers"]}
    assert "special_category_unconfirmed" not in blockers


# --- §8/§9/§20/§21: the rationale gate ----------------------------------


def test_weak_rationales_are_rejected_without_relying_on_length() -> None:
    """§8: the listed values, and a restatement that would pass a count."""
    for weak in ("ok", "none", "n/a", "test", "yes", "no", "done", "fine"):
        assert dpia_quality.rationale_problem(weak) is not None

    # Long enough to pass any character floor, and says nothing.
    assert (
        dpia_quality.rationale_problem(
            "There are no material privacy risks identified here because we "
            "have concluded that there are no material privacy risks in this "
            "particular case at this time."
        )
        is not None
    )
    # §21: engages with the specifics.
    assert dpia_quality.rationale_problem(STRONG_RATIONALE) is None


@pytest.mark.asyncio
async def test_a_weak_rationale_is_refused_over_the_api(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§20: "ok" does not pass."""
    workflow = await _dpia_for(
        client,
        "quality7@example.com",
        name="Employee leave administration",
        purpose="Administer employee leave",
        categories=["Absence dates"],
    )
    dpia_id = workflow["id"]
    for row in workflow["suggested_risks"]:
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{row['id']}/dismiss",
            json={"reason": "Covered by the existing HR access-control programme."},
        )

    refused = await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-conclusion",
        json={"rationale": "ok"},
    )
    assert refused.status_code == 422
    assert "rationale somebody could rely on" in _refused(refused)

    # §21: the substantive one is accepted.
    accepted = await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-conclusion",
        json={"rationale": STRONG_RATIONALE},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["risk_conclusion"] == "no_material_risks"


# --- §12: a sign-off is about particular words about particular facts ---


@pytest.mark.asyncio
async def test_an_approval_goes_stale_when_the_processing_changes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12: do not silently preserve approval on stale conclusions."""
    workflow = await _dpia_for(
        client,
        "quality8@example.com",
        name="Employee leave administration",
        purpose="Administer employee leave",
        categories=["Absence dates"],
    )
    dpia_id = workflow["id"]
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/sections/approve",
        json={"section": "necessity_assessment"},
    )

    # The ROPA entry gains categories after the sign-off. However the
    # record came to change, the approval was given against the old one.
    activity = await db_session.get(
        ProcessingActivity, uuid.UUID(workflow["activity_id"])
    )
    activity.data_categories = ["Absence dates", "Fit notes", "Medical certificates"]
    await db_session.commit()

    fresh = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert "necessity_assessment" in fresh["stale_sections"]
    codes = {b["code"] for b in fresh["completion_blockers"]}
    assert "necessity_assessment_stale" in codes


# --- §13/§22: completion needs both kinds of completeness ---------------


@pytest.mark.asyncio
async def test_completion_requires_content_as_well_as_workflow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§22: the whole gate, driven end to end."""
    workflow = await _dpia_for(
        client,
        "quality9@example.com",
        name="Employee medical-leave administration",
        purpose="Administer statutory and contractual medical leave obligations",
        categories=["Absence dates", "Fit notes"],
    )
    dpia_id = workflow["id"]

    # Health signals are detected even though categories exist.
    fresh = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert fresh["special_category_signals"]
    assert not fresh["missing_facts"]

    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/special-category",
        json={
            "confirmed": True,
            "rationale": "Fit notes are health data held for statutory sick pay.",
        },
    )
    for row in workflow["suggested_risks"]:
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{row['id']}/dismiss",
            json={"reason": "Covered by the existing HR access-control programme."},
        )
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-conclusion",
        json={"rationale": STRONG_RATIONALE},
    )
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/consultation",
        json={
            "performed": True,
            "party": "Jane Smith",
            "role": "DPO",
            "notes": "Advised that fit notes stay with HR and are not copied to line managers.",
        },
    )
    for section in dpia_workflow.NARRATIVE_SECTIONS:
        approved = await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/sections/approve",
            json={"section": section},
        )
        assert approved.status_code == 200, approved.text

    fresh = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert fresh["can_complete"] is True, fresh["completion_blockers"]

    completed = (
        await client.post(f"/api/v1/compliance/dpias/{dpia_id}/complete")
    ).json()
    assert completed["status"] == "completed"

    # §15: the record answers the questions asked of it.
    snapshot = completed["snapshot"]
    assert snapshot["processing"]["data_categories"] == ["Absence dates", "Fit notes"]
    assert snapshot["special_category"]["confirmed"] is True
    assert snapshot["special_category"]["decided_by"] == "Zach Warren"
    assert "statutory sick pay" in snapshot["special_category"]["rationale"]
    assert snapshot["risk_review"]["conclusion"] == "no_material_risks"
    assert "access is restricted" in snapshot["risk_review"]["rationale"]
    assert snapshot["consultation"]["party"] == "Jane Smith"
    assert not dpia_quality.is_instructional(
        snapshot["assessment"]["necessity_assessment"]["text"]
    )


# --- §16: history is flagged, never rewritten ---------------------------


@pytest.mark.asyncio
async def test_a_weakly_completed_dpia_is_flagged_and_kept(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§16: preserve the snapshot, recommend a quality review."""
    workflow = await _dpia_for(
        client,
        "quality10@example.com",
        name="Employee medical-leave administration",
        purpose="Administer medical leave",
        categories=["Absence dates"],
    )
    dpia_id = workflow["id"]

    # A DPIA as it would have completed before these gates existed.
    dpia = await db_session.get(DPIA, uuid.UUID(dpia_id))
    dpia.status = dpia_workflow.COMPLETED
    dpia.snapshot = {
        "processing": {
            "title": "Employee medical-leave administration",
            "purpose": "Administer medical leave",
            "data_categories": [],
        },
        "assessment": {
            "processing_description": {"text": "The processing exists to administer leave."},
            "necessity_assessment": {
                "text": "State why this processing is necessary to achieve it."
            },
            "proportionality_assessment": {
                "text": "Assess whether the data collected is limited to what the "
                "purpose requires."
            },
        },
        "risk_review": {"conclusion": "no_material_risks", "rationale": "ok"},
    }
    await db_session.commit()

    problems = dpia_completion.snapshot_quality_problems(dpia)
    assert any("guidance" in problem for problem in problems)
    assert any("rationale" in problem for problem in problems)
    assert any("personal-data categories" in problem for problem in problems)
    assert any("special-category" in problem for problem in problems)

    fresh = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert fresh["quality_review_reason"] is not None
    assert "would not pass those checks now" in fresh["quality_review_reason"]

    # The snapshot itself is untouched — the record still says what it
    # said on the day it was signed.
    assert fresh["status"] == "completed"
    assert fresh["snapshot"]["risk_review"]["rationale"] == "ok"
    assert (
        fresh["snapshot"]["assessment"]["necessity_assessment"]["text"]
        == "State why this processing is necessary to achieve it."
    )

    events = list(
        (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.object_id == dpia_id,
                    AuditEvent.action
                    == "compliance.dpia.quality_review_recommended",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
