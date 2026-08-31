"""EU AI Act Art. 4, from gap to resolved, without anyone attaching a file.

The reported failure was a remediation task that opened as an empty
shell. Fixing the shell is not enough on its own — a populated task that
never closes is the same dead end one screen later. So this walks the
whole loop the customer was promised:

    gap detected
        -> plan generated automatically
        -> task populated from the plan
        -> required evidence named
        -> a training record uploaded and read
        -> mapped to the control by the model, approved by the rules
        -> control reassessed automatically
        -> gap resolved, task closed, readiness moves

The gateway is stubbed with a scripted proposal so the assertions are
about *this code's* behaviour rather than a model's mood, and so the
test costs nothing to run. The routing decision that accepts the
proposal is the real one.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.evidence_ai import (
    DocumentAnalysis,
    ProposedMapping,
    suggest_evidence_mappings,
)
from app.compliance.models import Control
from app.core.models import File, Membership
from app.seed import _ensure_compliance_catalog

AI_LITERACY_TRAINING = """ACME AI SAAS - AI LITERACY TRAINING RECORD

Section 1 Programme
All staff who operate or oversee an AI system complete the AI literacy
course before they are granted access, covering capabilities, limits,
human oversight duties and how to escalate a bad output.

Section 2 Completion
The following people completed the course on 4 March: Dana Okafor
(Support Lead), Ravi Menon (Support), Ines Duarte (Engineering). Each
acknowledged the AI use policy in writing at completion.
"""


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


class _StubGateway:
    """Stands in for the model, returning whatever the test scripted."""

    def __init__(self, mappings: list[ProposedMapping]) -> None:
        self._mappings = mappings

    async def generate_structured(self, db, *, organization_id, requested_by, request, schema):  # type: ignore[no-untyped-def]
        return DocumentAnalysis(
            document_type="Training Record",
            document_domain="AI Governance",
            mappings=self._mappings,
        )


async def _signup(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"art4-{uuid.uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery",
            "full_name": "Acme Compliance Lead",
            "organization_name": f"Acme AI SaaS {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _organization_id(client: AsyncClient, db: AsyncSession) -> uuid.UUID:
    me = (await client.get("/api/v1/auth/me")).json()
    return (
        await db.execute(
            select(Membership.organization_id).where(
                Membership.user_id == uuid.UUID(me["id"])
            )
        )
    ).scalar_one()


async def _upload(client: AsyncClient, db: AsyncSession, filename: str, body: str) -> File:
    response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": filename,
            "content_type": "text/plain",
            "size_bytes": len(body),
            "classification": "confidential",
        },
    )
    assert response.status_code == 200, response.text
    record = await db.get(File, uuid.UUID(response.json()["file_id"]))
    assert record is not None
    return record


async def _control_index(db: AsyncSession, organization_id: uuid.UUID, title: str) -> int:
    """The prompt numbers controls positionally, so a scripted proposal has
    to reference the same order the prompt was built from."""
    controls = list(
        (
            await db.execute(
                select(Control)
                .where(Control.organization_id == organization_id)
                .order_by(Control.created_at, Control.id)
            )
        )
        .scalars()
        .all()
    )
    for index, control in enumerate(controls, start=1):
        if control.title == title:
            return index
    raise AssertionError(f"No control titled {title!r}. Have: {[c.title for c in controls]}")


async def test_art_4_walks_from_gap_to_resolved(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client)
    organization_id = await _organization_id(client, db_session)

    # 1. A company that runs an AI system, so Art. 4 is genuinely in scope.
    registered = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Support Copilot",
            "vendor": "OpenAI",
            "purpose": "Drafts replies to customer support tickets.",
            "risk_classification": "limited",
        },
    )
    assert registered.status_code == 201, registered.text

    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    framework_id = next(f["id"] for f in frameworks if f["key"] == "eu_ai_act")
    await client.put(
        f"/api/v1/compliance/frameworks/{framework_id}/activation", json={"active": True}
    )

    # 2. Gap detected.
    result = (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()
    art4 = next(r for r in result["requirements"] if r["reference_code"] == "Art. 4")
    assert art4["gap_id"], "Art. 4 applies to anyone operating an AI system"
    readiness_before = result["readiness"]["percent"]

    # 3. Remediation generated by Veyntra, with no button pressed.
    gap = (await client.get(f"/api/v1/compliance/gaps/{art4['gap_id']}")).json()
    plan = gap["remediation_plan"]
    assert plan is not None
    assert plan["checklist"], "the checklist was empty — the reported bug"
    assert plan["owner"] == "HR / People"
    assert any(
        "completion" in item.lower() or "attendance" in item.lower()
        for item in plan["required_evidence"]
    ), plan["required_evidence"]

    # 4. Task populated from the plan.
    task = (
        await client.post(f"/api/v1/compliance/gaps/{gap['id']}/task", json={})
    ).json()
    assert len(task["checklist"]) == len(plan["checklist"])
    assert "PROBLEM" in task["description"]
    assert task["status"] == "open"

    activity = (await client.get(f"/api/v1/tasks/{task['id']}/activity")).json()
    assert any("Remediation plan generated" in e["label"] for e in activity)

    # 5. The training record arrives. Nobody attaches it to anything.
    document = await _upload(
        client, db_session, "ai-literacy-training.txt", AI_LITERACY_TRAINING
    )
    literacy_index = await _control_index(
        db_session, organization_id, "Ensure staff competence in AI use"
    )
    await suggest_evidence_mappings(
        db_session,
        organization_id=organization_id,
        file_record=document,
        file_bytes=AI_LITERACY_TRAINING.encode(),
        actor_user_id=None,
        gateway=_StubGateway(
            [
                ProposedMapping(
                    control_index=literacy_index,
                    section_index=2,
                    confidence=0.95,
                    rationale="Section 2 names each person who completed the course.",
                    evidence_type="training_record",
                    quoted_passage=(
                        "The following people completed the course on 4 March"
                    ),
                )
            ]
        ),
    )
    await db_session.commit()

    # The rules accepted it: a verified quote, high confidence, and Art. 4
    # is not one of the sensitivity-gated requirements.
    suggestions = (await client.get("/api/v1/compliance/evidence/suggestions")).json()
    assert not any(s["status"] == "proposed" for s in suggestions), (
        "a verified high-confidence training record should not need a human"
    )

    # The document arriving is visible from the task, which is the point of
    # not making the customer attach it by hand.
    activity = (await client.get(f"/api/v1/tasks/{task['id']}/activity")).json()
    assert any("New evidence detected" in e["label"] for e in activity), [
        e["label"] for e in activity
    ]

    # 6. Reassessment. Run explicitly here because the endpoint schedules it
    # as a background task after the response, which the test client does
    # not run — the deterministic part is what is under test.
    from app.compliance.assessment import reassess_frameworks_for_control

    control_id = (
        await db_session.execute(
            select(Control.id).where(
                Control.organization_id == organization_id,
                Control.title == "Ensure staff competence in AI use",
            )
        )
    ).scalar_one()

    class _Session:
        def __init__(self, session: AsyncSession) -> None:
            self._session = session

        async def __aenter__(self) -> AsyncSession:
            return self._session

        async def __aexit__(self, *args: object) -> None:
            return None

    await reassess_frameworks_for_control(
        control_id,
        organization_id=organization_id,
        actor_user_id=None,
        session_factory=lambda: _Session(db_session),
    )

    # 7. The evidence is on file, so the task is no longer waiting on the
    # customer to find a document — it is waiting on a human verdict. The
    # gap does NOT resolve here: evidence existing is not the same as
    # somebody having concluded the control passes, and closing it now
    # would make the product assert a position nobody signed.
    pending = (await client.get(f"/api/v1/compliance/gaps/{gap['id']}")).json()
    assert pending["status"] != "resolved"
    assert pending["kind"] == "evidence_partial", pending["summary"]

    in_review = (await client.get(f"/api/v1/tasks/{task['id']}")).json()
    assert in_review["status"] == "in_progress"

    # And the refreshed plan names the document it read, rather than still
    # asking for evidence the customer supplied last week.
    assert "ai-literacy-training.txt" in pending["remediation_plan"]["evidence_reviewed"]

    # 8. A person records the verdict. This is the gate that never moves:
    # the arithmetic is automated, the conclusion is not.
    assessed = await client.post(
        f"/api/v1/compliance/controls/{control_id}/assessments",
        json={"status": "pass", "notes": "Completion records name every operator."},
    )
    assert assessed.status_code == 201, assessed.text

    # 9. The gap closes, the task closes with it, and readiness moves.
    after = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    resolved = (await client.get(f"/api/v1/compliance/gaps/{gap['id']}")).json()
    assert resolved["status"] == "resolved", resolved["summary"]

    closed = (await client.get(f"/api/v1/tasks/{task['id']}")).json()
    assert closed["status"] == "done", "a resolved gap must not leave its task open"

    assert after["readiness"]["percent"] > readiness_before

    # 10. The whole thing readable from the task, in order, in sentences.
    activity = (await client.get(f"/api/v1/tasks/{task['id']}/activity")).json()
    labels = [e["label"] for e in activity]
    for expected in (
        "Gap identified",
        "Remediation plan generated",
        "Remediation task raised",
        "New evidence detected",
        "Control reassessed",
        "Ready for review",
        "Gap resolved",
    ):
        assert any(expected in label for label in labels), (expected, labels)
    assert any("Closed automatically" in label for label in labels)
    for label in labels:
        assert "compliance." not in label and "core.task." not in label
