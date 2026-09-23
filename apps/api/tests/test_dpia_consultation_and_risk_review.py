"""One consultation state, and a risk review that can conclude "none".

Two contradictions the DPIA page could show at once, both fixed here.

The consultation had two states for one fact: a recorded decision, and a
sign-off on `consultation_notes` as an Article 35(7) section. So a DPIA
could display "No consultation performed" beside "Nobody has approved
the consultation record", and completion demanded approval of a decision
that had already been made.

And a DPIA could not conclude that nothing was risky. Completion
required at least one risk on the register, so a reviewer who read every
candidate and judged none material could only finish by inventing one —
a worse record than the honest one. "Nobody looked" and "looked, and
found none" are different claims that a count of zero cannot separate.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance import dpia_workflow
from app.compliance.models import DPIA, Risk


# A rationale that engages with the processing rather than restating
# the conclusion — the quality gate refuses anything less.
STRONG_RATIONALE = (
    "The processing is limited to what the recorded purpose requires, "
        "access is restricted to the team that actions it, records are "
        "retained for the recorded period and then deleted, no automated "
        "decisions are made about individuals, and no data reaches a "
        "processor outside the organization, so the remaining impact on "
        "individuals is minimal."
)


def _refused(response) -> str:
    return response.json()["error"]["message"]


async def _with_retention(
    client: AsyncClient, db_session: AsyncSession, activity_id: str
) -> None:
    """Give the activity a retention period.

    The helper below deliberately omits one so that Veyntra proposes a
    risk about it. Completion now refuses without it — proportionality is
    judged partly on how long data is kept — so the tests that go all the
    way to completion fill it in first.
    """
    from app.compliance.models import ProcessingActivity

    activity = await db_session.get(ProcessingActivity, uuid.UUID(activity_id))
    activity.retention_period = "24 months"
    await db_session.commit()


async def _plain_activity(client: AsyncClient, email: str) -> dict:
    """An organization and one unremarkable processing activity.

    Nothing about it draws an AI system or a processor, so Veyntra
    proposes exactly one risk (no retention period is recorded) — few
    enough that these tests are about the conclusion rather than triage.
    """
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )
    activity = (
        await client.post(
            "/api/v1/compliance/processing-activities",
            json={
                "name": "Support ticket triage",
                "purpose": "Route incoming customer support tickets to the right team.",
                "legal_basis": "contract",
                "data_subjects": "Customers",
                "data_categories": ["Contact details"],
            },
        )
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


async def _approve_narrative(client: AsyncClient, dpia_id: str) -> None:
    for section in dpia_workflow.NARRATIVE_SECTIONS:
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/sections/approve",
            json={"section": section},
        )


async def _clear_suggestions(client: AsyncClient, dpia_id: str) -> None:
    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    for row in workflow["suggested_risks"]:
        if row["status"] == "suggested":
            await client.post(
                f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{row['id']}/dismiss",
                json={"reason": "Covered by the existing access-control programme."},
            )


# --- §1/§5/§6: one consultation state -----------------------------------


@pytest.mark.asyncio
async def test_the_consultation_section_cannot_be_approved_separately(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5: one source of truth, so the second one is refused.

    Approving `consultation_notes` as a section is what let the page
    hold two answers about the same fact.
    """
    workflow = await _plain_activity(client, "consult1@example.com")
    response = await client.post(
        f"/api/v1/compliance/dpias/{workflow['id']}/sections/approve",
        json={"section": "consultation_notes"},
    )
    assert response.status_code == 422
    assert "recording the consultation decision" in _refused(response)


@pytest.mark.asyncio
async def test_consultation_starts_undecided_and_blocks_on_that(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2/§14: the blocker names the decision, not a missing approval."""
    workflow = await _plain_activity(client, "consult2@example.com")
    assert workflow["consultation_state"] == "not_decided"

    codes = {b["code"] for b in workflow["completion_blockers"]}
    assert "consultation_not_recorded" in codes
    # And never the old approval blocker, which asked for a second
    # decision about a question nobody had answered once.
    assert "consultation_notes_unreviewed" not in codes
    assert "consultation_notes_empty" not in codes


@pytest.mark.asyncio
async def test_a_performed_consultation_resolves_it_without_a_second_step(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3/§18 Test A: the record itself satisfies the review."""
    workflow = await _plain_activity(client, "consult3@example.com")
    dpia_id = workflow["id"]

    recorded = (
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/consultation",
            json={
                "performed": True,
                "party": "Jane Smith",
                "role": "DPO",
                "consulted_at": "2026-09-02T00:00:00Z",
                "notes": "Proceed subject to retention and minimization controls.",
            },
        )
    ).json()

    assert recorded["consultation_state"] == "consultation_performed"
    assert recorded["consulted_party"] == "Jane Smith"
    assert recorded["consulted_role"] == "DPO"
    assert recorded["consultation_recorded_by_name"] == "Zach Warren"
    assert recorded["consultation_recorded_at"] is not None
    # The advice is the section content — one record, not two.
    assert "retention and minimization" in recorded["consultation_notes"]

    codes = {b["code"] for b in recorded["completion_blockers"]}
    assert "consultation_not_recorded" not in codes
    assert not any(code.startswith("consultation_notes") for code in codes)


@pytest.mark.asyncio
async def test_recording_a_consultation_still_needs_who(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow = await _plain_activity(client, "consult4@example.com")
    response = await client.post(
        f"/api/v1/compliance/dpias/{workflow['id']}/consultation",
        json={"performed": True, "notes": "Some advice."},
    )
    assert response.status_code == 422
    assert "who was consulted" in _refused(response)


# --- §4: declining is a decision, and it needs a reason -----------------


@pytest.mark.asyncio
async def test_no_consultation_needs_a_reason_and_then_resolves(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4/§18 Test B: reason required, and no duplicate approval blocker."""
    workflow = await _plain_activity(client, "consult5@example.com")
    dpia_id = workflow["id"]

    refused = await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/consultation",
        json={"performed": False},
    )
    assert refused.status_code == 422
    assert "requires a reason" in _refused(refused)

    recorded = (
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/consultation",
            json={
                "performed": False,
                "notes": (
                    "No DPO consultation was considered necessary for this "
                    "processing after the screening and risk review."
                ),
            },
        )
    ).json()

    assert recorded["consultation_state"] == "no_consultation"
    assert recorded["consultation_recorded_by_name"] == "Zach Warren"
    # §6: no leftover approval blocker for a resolved decision.
    codes = {b["code"] for b in recorded["completion_blockers"]}
    assert "consultation_not_recorded" not in codes
    assert not any("consultation" in code for code in codes)


@pytest.mark.asyncio
async def test_recording_a_consultation_clears_a_stale_section_sign_off(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A sign-off from before this change described words that no longer
    govern anything, and would render as "Approved" beside a decision
    made afterwards."""
    workflow = await _plain_activity(client, "consult6@example.com")
    dpia_id = workflow["id"]

    dpia = await db_session.get(DPIA, uuid.UUID(dpia_id))
    dpia.section_reviews = {
        "consultation_notes": {"approved_by": None, "approved_at": "2026-01-01T00:00:00Z"}
    }
    await db_session.commit()

    after = (
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/consultation",
            json={"performed": False, "notes": "Not needed for routine triage."},
        )
    ).json()
    assert [row["section"] for row in after["section_reviews"]] == []


# --- §7/§9/§11: the risk review can conclude "none" ---------------------


@pytest.mark.asyncio
async def test_an_unreviewed_risk_assessment_blocks_and_says_so(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§14/§18 Test F: the blocker names the review, not a missing risk."""
    workflow = await _plain_activity(client, "risk1@example.com")
    assert workflow["risk_conclusion"] == "not_reviewed"

    codes = {b["code"] for b in workflow["completion_blockers"]}
    assert "risk_review_incomplete" in codes
    # The old wording told somebody to invent a risk.
    assert "no_risks" not in codes
    message = next(
        b["message"] for b in workflow["completion_blockers"]
        if b["code"] == "risk_review_incomplete"
    )
    assert "has not been reviewed" in message
    assert "none are material" in message


@pytest.mark.asyncio
async def test_dismissing_every_suggestion_allows_the_no_material_conclusion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9/§18 Test D: reviewed, none accepted, and a rationale recorded."""
    workflow = await _plain_activity(client, "risk2@example.com")
    dpia_id = workflow["id"]
    assert len(workflow["suggested_risks"]) >= 1

    await _clear_suggestions(client, dpia_id)
    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert workflow["can_conclude_no_material_risks"] is True
    # Still not a completed review — dismissing is not concluding.
    assert workflow["risk_conclusion"] == "not_reviewed"

    concluded = (
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/risk-conclusion",
            json={
                "rationale": (
                    "The processing is limited to customer support, no "
                    "automated decisions are made, and existing safeguards "
                    "reduce the identified concerns below the organization's "
                    "risk threshold."
                )
            },
        )
    ).json()

    assert concluded["risk_conclusion"] == "no_material_risks"
    assert concluded["risk_reviewed_by_name"] == "Zach Warren"
    assert concluded["risk_reviewed_at"] is not None
    assert "risk threshold" in concluded["risk_conclusion_rationale"]
    # §12: nothing to rate, and not "not assessed" either.
    assert concluded["inherent_risk"] is None
    assert concluded["residual_risk"] is None

    codes = {b["code"] for b in concluded["completion_blockers"]}
    assert "risk_review_incomplete" not in codes
    assert "no_risks" not in codes


@pytest.mark.asyncio
async def test_the_conclusion_needs_a_rationale(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow = await _plain_activity(client, "risk3@example.com")
    await _clear_suggestions(client, workflow["id"])
    response = await client.post(
        f"/api/v1/compliance/dpias/{workflow['id']}/risk-conclusion",
        json={"rationale": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_the_conclusion_is_refused_while_a_suggestion_is_open(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The claim is about a review that finished."""
    workflow = await _plain_activity(client, "risk4@example.com")
    response = await client.post(
        f"/api/v1/compliance/dpias/{workflow['id']}/risk-conclusion",
        json={"rationale": "Nothing material here."},
    )
    assert response.status_code == 422
    assert "waiting on a decision" in _refused(response)


@pytest.mark.asyncio
async def test_the_conclusion_is_refused_when_a_risk_is_on_the_register(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: a register with risks contradicts "none were material"."""
    workflow = await _plain_activity(client, "risk5@example.com")
    dpia_id = workflow["id"]
    suggestion = workflow["suggested_risks"][0]
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{suggestion['id']}/approve",
        json={"likelihood": "low", "impact": "low"},
    )
    await _clear_suggestions(client, dpia_id)

    response = await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-conclusion",
        json={"rationale": "Actually nothing material."},
    )
    assert response.status_code == 422
    assert "on its register" in _refused(response)


@pytest.mark.asyncio
async def test_accepting_a_risk_records_that_risks_were_identified(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§18 Test C: the ordinary path still concludes, without a new step."""
    workflow = await _plain_activity(client, "risk6@example.com")
    dpia_id = workflow["id"]
    suggestion = workflow["suggested_risks"][0]

    after = (
        await client.post(
            f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{suggestion['id']}/approve",
            json={"likelihood": "medium", "impact": "high"},
        )
    ).json()

    assert after["risk_conclusion"] == "risks_identified"
    assert after["inherent_risk"] == "high"
    assert after["can_conclude_no_material_risks"] is False
    codes = {b["code"] for b in after["completion_blockers"]}
    assert "risk_review_incomplete" not in codes


@pytest.mark.asyncio
async def test_adding_a_risk_by_hand_also_completes_the_review(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10/§18 Test E: "Add risk" is a reviewed assessment too."""
    workflow = await _plain_activity(client, "risk7@example.com")
    dpia_id = workflow["id"]

    created = await client.post(
        "/api/v1/compliance/risks",
        json={
            "title": "Support content may be over-retained",
            "likelihood": "low",
            "impact": "medium",
            "dpia_id": dpia_id,
        },
    )
    assert created.status_code == 201, created.text

    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert workflow["risk_conclusion"] == "risks_identified"


@pytest.mark.asyncio
async def test_a_risk_accepted_after_the_conclusion_overrides_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A DPIA must not claim it found nothing while listing what it found."""
    workflow = await _plain_activity(client, "risk8@example.com")
    dpia_id = workflow["id"]
    await _clear_suggestions(client, dpia_id)
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-conclusion",
        json={"rationale": "Nothing material after review."},
    )

    created = await client.post(
        "/api/v1/compliance/risks",
        json={
            "title": "A risk somebody found afterwards",
            "likelihood": "high",
            "impact": "high",
            "dpia_id": dpia_id,
        },
    )
    assert created.status_code == 201

    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert workflow["risk_conclusion"] == "risks_identified"
    assert workflow["risk_conclusion_rationale"] is None


# --- §13: completion, without an invented risk --------------------------


@pytest.mark.asyncio
async def test_a_dpia_completes_with_no_risks_when_the_review_concluded_none(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The whole point: an honest empty register can finish."""
    workflow = await _plain_activity(client, "risk9@example.com")
    dpia_id = workflow["id"]
    await _with_retention(client, db_session, workflow["activity_id"])

    await _clear_suggestions(client, dpia_id)
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-conclusion",
        json={"rationale": STRONG_RATIONALE},
    )
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/consultation",
        json={"performed": False, "notes": "No DPO appointed; routine processing."},
    )
    await _approve_narrative(client, dpia_id)

    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert workflow["can_complete"] is True, workflow["completion_blockers"]

    completed = (
        await client.post(f"/api/v1/compliance/dpias/{dpia_id}/complete")
    ).json()
    assert completed["status"] == "completed"

    snapshot = completed["snapshot"]
    assert snapshot["risks"] == []
    # §16: what was concluded is on the record, not inferred from a zero.
    assert snapshot["risk_review"]["conclusion"] == "no_material_risks"
    assert "remaining impact on individuals" in snapshot["risk_review"]["rationale"]
    assert snapshot["risk_review"]["reviewed_by"] == "Zach Warren"
    assert snapshot["consultation"]["state"] == "no_consultation"
    assert "No DPO appointed" in snapshot["consultation"]["notes"]
    assert snapshot["consultation"]["recorded_by"] == "Zach Warren"


@pytest.mark.asyncio
async def test_risks_still_have_to_add_up_when_there_are_any(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: nothing about the ordinary path got looser."""
    workflow = await _plain_activity(client, "risk10@example.com")
    dpia_id = workflow["id"]
    await _with_retention(client, db_session, workflow["activity_id"])
    suggestion = workflow["suggested_risks"][0]
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-suggestions/{suggestion['id']}/approve",
        json={"likelihood": "low", "impact": "low"},
    )
    await _clear_suggestions(client, dpia_id)
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/consultation",
        json={"performed": False, "notes": "Not needed."},
    )
    await _approve_narrative(client, dpia_id)

    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    codes = {b["code"] for b in workflow["completion_blockers"]}
    # A risk nobody reassessed still blocks, exactly as before.
    assert "risks_incomplete" in codes
    assert workflow["can_complete"] is False

    risk = (
        await db_session.execute(
            select(Risk).where(Risk.dpia_id == uuid.UUID(dpia_id))
        )
    ).scalars().one()
    await client.patch(
        f"/api/v1/compliance/risks/{risk.id}/residual",
        json={"residual_likelihood": "low", "residual_impact": "low"},
    )
    await client.post(f"/api/v1/compliance/dpias/{dpia_id}/recalculate-residual")

    workflow = (
        await client.get(f"/api/v1/compliance/dpias/{dpia_id}/workflow")
    ).json()
    assert workflow["can_complete"] is True, workflow["completion_blockers"]


# --- §16: every decision reaches the audit log --------------------------


@pytest.mark.asyncio
async def test_the_decisions_are_audited_with_actor_and_time(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    workflow = await _plain_activity(client, "audit1@example.com")
    dpia_id = workflow["id"]

    await _clear_suggestions(client, dpia_id)
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-conclusion",
        json={"rationale": STRONG_RATIONALE},
    )
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/consultation",
        json={"performed": False, "notes": "Not needed."},
    )

    events = list(
        (
            await db_session.execute(
                select(AuditEvent).where(AuditEvent.object_id == dpia_id)
            )
        )
        .scalars()
        .all()
    )
    actions = {event.action for event in events}
    assert "compliance.dpia.risk_dismissed" in actions
    assert "compliance.dpia.no_material_risks_concluded" in actions
    assert "compliance.dpia.consultation_not_performed" in actions
    for event in events:
        assert event.actor_user_id is not None
        assert event.created_at is not None
        assert event.object_id == dpia_id


@pytest.mark.asyncio
async def test_changing_a_decision_is_audited_as_a_change_with_before_state(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§11: revising an answer is a different event from answering.

    An auditor reading the log should not have to infer from timestamps
    which happened, and should be able to see what the record said before.
    """
    workflow = await _plain_activity(client, "audit2@example.com")
    dpia_id = workflow["id"]

    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/consultation",
        json={"performed": False, "notes": "Not needed for routine triage."},
    )
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/consultation",
        json={
            "performed": True,
            "party": "Jane Smith",
            "role": "DPO",
            "notes": "Reviewed after all; proceed with minimisation.",
        },
    )

    events = list(
        (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.object_id == dpia_id,
                    AuditEvent.action == "compliance.dpia.consultation_changed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    changed = events[0]
    assert changed.before_state["state"] == "no_consultation"
    assert "Not needed" in changed.before_state["notes"]
    assert changed.after_state["state"] == "consultation_performed"
    assert changed.after_state["party"] == "Jane Smith"


@pytest.mark.asyncio
async def test_a_risk_overturning_the_conclusion_is_audited_as_a_change(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§11: the rationale that no longer holds is preserved in the log.

    Dropping it from the record silently would erase why somebody had
    concluded otherwise.
    """
    workflow = await _plain_activity(client, "audit3@example.com")
    dpia_id = workflow["id"]

    await _clear_suggestions(client, dpia_id)
    await client.post(
        f"/api/v1/compliance/dpias/{dpia_id}/risk-conclusion",
        json={"rationale": STRONG_RATIONALE},
    )
    await client.post(
        "/api/v1/compliance/risks",
        json={
            "title": "A risk found later",
            "likelihood": "high",
            "impact": "high",
            "dpia_id": dpia_id,
        },
    )

    events = list(
        (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.object_id == dpia_id,
                    AuditEvent.action == "compliance.dpia.risk_conclusion_changed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    changed = events[0]
    assert changed.before_state["conclusion"] == "no_material_risks"
    assert "remaining impact on individuals" in changed.before_state["rationale"]
    assert changed.after_state["conclusion"] == "risks_identified"
