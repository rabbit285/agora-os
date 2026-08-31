"""An audit the auditor reviews rather than reconstructs.

The audit used to be a title and a blank finding form. Everything needed
to reach a finding — which requirements bind this organization, which
control answers each, what evidence is on file, what Veyntra makes of it
— existed elsewhere and was never brought to the audit.

These pin the workflow that replaces it: Veyntra prepares from the
compliance state that already exists, the auditor decides on exceptions,
a decision carries its own context into the finding, remediation is
reused rather than duplicated, and closure is a human verification that
records what it relied on.

And the state bug they were written alongside: an audit sitting at
"Planned" with "Completed 8/26/2026" printed beside it, because the
completion stamp was written on the way to completed and never cleared on
the way back.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance import audit_state, audit_workspace
from app.compliance.audit_findings import DecisionRefused, record_decision
from app.compliance.models import (
    Audit,
    AuditFinding,
    AuditItem,
    ComplianceGap,
    Control,
    ControlMapping,
    Framework,
    Requirement,
)
from app.core.models import Task


async def _signup(client: AsyncClient, email: str, org: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


# The 18 clauses of ISO 42001 the product's catalog carries. Built here
# rather than depending on seed data so the scope is stated in the test
# that asserts against it: "18 applicable requirements" should be
# something a reader can count, not a number from a fixture elsewhere.
_CLAUSES = [
    ("4.1", "Understanding the organization and its context"),
    ("4.2", "Understanding the needs and expectations of interested parties"),
    ("4.3", "Determining the scope of the AI management system"),
    ("4.4", "AI management system"),
    ("5.1", "Leadership and commitment"),
    ("5.2", "AI policy"),
    ("5.3", "Roles, responsibilities and authorities"),
    ("6.1", "Actions to address risks and opportunities"),
    ("6.2", "AI objectives and planning to achieve them"),
    ("7.1", "Resources"),
    ("7.2", "Competence"),
    ("7.4", "Communication"),
    ("7.5", "Documented information"),
    ("8.1", "Operational planning and control"),
    ("8.2", "AI risk assessment"),
    ("9.1", "Monitoring, measurement, analysis and evaluation"),
    ("9.2", "Internal audit"),
    ("10.1", "Continual improvement and nonconformity"),
]


async def _framework(db: AsyncSession, key: str = "iso42001") -> Framework:
    """The framework under audit, with its clauses.

    Reused when it already exists so several audits in one test scope
    against the same catalog rows, the way they do in production.
    """
    framework = (
        await db.execute(select(Framework).where(Framework.key == key))
    ).scalars().first()
    if framework is None:
        framework = Framework(key=key, name="ISO 42001", description=None)
        db.add(framework)
        await db.flush()
    existing = {
        code
        for code in (
            await db.execute(
                select(Requirement.reference_code).where(
                    Requirement.framework_id == framework.id
                )
            )
        ).scalars()
    }
    for code, title in _CLAUSES:
        if code in existing:
            continue
        db.add(
            Requirement(
                framework_id=framework.id,
                reference_code=code,
                title=title,
                description=None,
            )
        )
    await db.flush()
    return framework


async def _audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    framework: Framework | None = None,
    status: str = "planned",
) -> Audit:
    audit = Audit(
        organization_id=org_id,
        title="ISO 42001 Internal Audit",
        framework_id=framework.id if framework else None,
        auditor_name="Zach Warren",
        scope="AI governance controls and evidence",
    )
    audit_state.apply_status(audit, status)
    db.add(audit)
    await db.flush()
    return audit


# --- §1/§29 the state bug ----------------------------------------------


@pytest.mark.parametrize(
    ("status", "started", "completed"),
    [
        ("planned", False, False),
        ("in_progress", True, False),
        ("completed", True, True),
    ],
)
def test_the_timestamps_are_the_state(
    status: str, started: bool, completed: bool
) -> None:
    audit = Audit(title="A", organization_id=uuid.uuid4())
    audit_state.apply_status(audit, status)
    assert (audit.started_at is not None) is started
    assert (audit.completed_at is not None) is completed
    assert audit_state.check_invariants(audit) == []


def test_going_backwards_clears_what_stopped_being_true() -> None:
    """The reported screen: "Planned" over "Completed 8/26/2026".

    The completion stamp was written on the way to completed and left
    behind on the way back, so both the badge and the date were reading
    the database correctly and disagreeing.
    """
    audit = Audit(title="A", organization_id=uuid.uuid4())
    audit_state.apply_status(audit, "completed")
    assert audit.completed_at is not None

    audit_state.apply_status(audit, "planned")
    assert audit.completed_at is None
    assert audit.started_at is None
    assert audit_state.check_invariants(audit) == []

    # And reopening a finished audit keeps the original start: the
    # engagement did begin when it began.
    audit_state.apply_status(audit, "in_progress")
    first_start = audit.started_at
    audit_state.apply_status(audit, "completed")
    audit_state.apply_status(audit, "in_progress")
    assert audit.started_at == first_start
    assert audit.completed_at is None


def test_the_contradiction_is_named_rather_than_assumed() -> None:
    audit = Audit(title="A", organization_id=uuid.uuid4(), status="planned")
    audit.completed_at = audit_state._now()
    problems = audit_state.check_invariants(audit)
    assert problems, "a planned audit with a completion time is inconsistent"
    assert "not been completed" in " ".join(problems)


# --- §3 preparation ----------------------------------------------------


@pytest.mark.anyio
async def test_the_audit_opens_on_prepared_work(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§28: creating it against a framework scopes it from what exists."""
    org_id = await _signup(client, f"prep-{uuid.uuid4().hex[:8]}@example.com", "Prep Org")
    framework = await _framework(db_session)
    await db_session.commit()

    response = await client.post(
        "/api/v1/compliance/audits",
        json={
            "title": "ISO 42001 Internal Audit",
            "framework_id": str(framework.id),
            "auditor_name": "Zach Warren",
            "scope": "AI governance controls and evidence",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()

    # §1: a new audit has not started and has certainly not finished.
    assert body["status"] == "planned"
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert body["scope"] == "AI governance controls and evidence"
    # §3: not a blank page.
    assert body["prepared_at"] is not None
    assert body["progress"]["scoped"] == 18
    assert body["progress"]["reviewed"] == 0

    detail = (await client.get(f"/api/v1/compliance/audits/{body['id']}")).json()
    assert detail["sections"], "the workspace groups the scope into sections"
    scoped = sum(len(section["items"]) for section in detail["sections"])
    assert scoped == 18

    # §6: a row carries enough to decide on without leaving the page.
    row = detail["sections"][0]["items"][0]
    for field in (
        "reference_code",
        "requirement_title",
        "prepared_status",
        "prepared_status_label",
        "prepared_why",
        "evidence_snapshot",
    ):
        assert field in row, field
    assert row["decision"] is None


@pytest.mark.anyio
async def test_preparing_twice_reconciles_rather_than_duplicating(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§30: retries are safe at the data level, not merely unlikely."""
    org_id = await _signup(client, f"idem-{uuid.uuid4().hex[:8]}@example.com", "Idem Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework)
    await db_session.commit()

    first = await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    second = await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    await db_session.commit()

    assert first.created == 18
    assert second.created == 0
    assert second.updated == 18

    rows = int(
        (
            await db_session.execute(
                select(func.count(AuditItem.id)).where(AuditItem.audit_id == audit.id)
            )
        ).scalar_one()
    )
    assert rows == 18


@pytest.mark.anyio
async def test_re_preparing_never_erases_a_decision(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An auditor's conclusion is not a cache to be refreshed."""
    org_id = await _signup(client, f"keep-{uuid.uuid4().hex[:8]}@example.com", "Keep Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework)
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    await db_session.commit()

    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    await record_decision(
        db_session,
        audit=audit,
        item=item,
        decision="observation",
        note="Documented, and worth watching.",
        actor_user_id=None,
    )
    snapshot = item.prepared_why
    await db_session.commit()

    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    await db_session.commit()
    await db_session.refresh(item)

    assert item.decision == "observation"
    assert item.decision_note == "Documented, and worth watching."
    # The snapshot they decided from stands too — refreshing it would
    # leave a conclusion attached to evidence nobody saw.
    assert item.prepared_why == snapshot


@pytest.mark.anyio
async def test_an_audit_with_no_framework_has_nothing_to_scope(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"nofw-{uuid.uuid4().hex[:8]}@example.com", "NoFw Org")
    audit = await _audit(db_session, org_id, framework=None)
    await db_session.commit()

    report = await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    assert report.applicable == 0

    # And the endpoint says so rather than silently doing nothing.
    response = await client.post(f"/api/v1/compliance/audits/{audit.id}/prepare")
    assert response.status_code == 422
    assert "no framework" in response.json()["error"]["message"]


# --- §5 exceptions first ------------------------------------------------


def test_rows_sort_the_way_the_standard_is_numbered() -> None:
    codes = ["10.1", "4.1", "9.3", "6.1", "A.5.2"]
    assert sorted(codes, key=audit_workspace.code_key) == [
        "4.1",
        "6.1",
        "9.3",
        "10.1",
        "A.5.2",
    ]


@pytest.mark.parametrize(
    ("prepared_status", "expected"),
    [
        ("not_assessed", "known_gaps"),
        ("evidence_missing", "known_gaps"),
        ("assessment_failed", "known_gaps"),
        ("needs_review", "needs_verification"),
        ("deficient", "insufficient_evidence"),
        ("satisfied", "satisfied"),
    ],
)
def test_each_state_lands_in_its_section(prepared_status: str, expected: str) -> None:
    item = AuditItem(prepared_status=prepared_status)
    assert audit_workspace.section_for(item) == expected


def test_evidence_arriving_after_the_audit_moves_the_row() -> None:
    """§5: what changed since you looked is its own pile."""
    item = AuditItem(prepared_status="satisfied")
    assert audit_workspace.section_for(item, has_new_evidence=True) == "changed_evidence"
    # Unless the auditor has already ruled on it — a decided row is not
    # outstanding work however much evidence arrives afterwards.
    item.decision = "no_finding"
    assert audit_workspace.section_for(item, has_new_evidence=True) == "satisfied"


# --- §8/§9 the decision, and what it carries ---------------------------


@pytest.mark.anyio
async def test_a_finding_inherits_the_row_it_came_from(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9: nobody retypes the requirement, control or evidence."""
    org_id = await _signup(client, f"ctx-{uuid.uuid4().hex[:8]}@example.com", "Ctx Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework)
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    await db_session.commit()

    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    item.control_title = "Operate an AI risk management process"
    item.evidence_snapshot = [
        {"evidence_id": str(uuid.uuid4()), "title": "AI Governance Policy v2.0"}
    ]
    await db_session.flush()

    result = await record_decision(
        db_session,
        audit=audit,
        item=item,
        decision="major",
        note=(
            "The AI risk process is documented, but no evidence of periodic "
            "execution was found."
        ),
        actor_user_id=None,
    )
    await db_session.commit()

    finding = result.finding
    assert finding is not None
    assert finding.requirement_id == item.requirement_id
    assert finding.requirement_code == item.reference_code
    assert finding.control_title == "Operate an AI risk management process"
    assert finding.severity == "high"
    # What the auditor was actually looking at, frozen.
    assert finding.evidence_snapshot[0]["title"] == "AI Governance Policy v2.0"
    assert item.finding_id == finding.id


@pytest.mark.anyio
async def test_a_finding_needs_a_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"why-{uuid.uuid4().hex[:8]}@example.com", "Why Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework)
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    await db_session.commit()

    with pytest.raises(DecisionRefused, match="needs a reason"):
        await record_decision(
            db_session,
            audit=audit,
            item=item,
            decision="major",
            note="   ",
            actor_user_id=None,
        )

    # A clean result needs no defence.
    result = await record_decision(
        db_session,
        audit=audit,
        item=item,
        decision="no_finding",
        note=None,
        actor_user_id=None,
    )
    assert result.finding is None


@pytest.mark.anyio
async def test_changing_the_decision_moves_the_one_finding(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§30, and an auditor correcting themselves.

    Deciding twice must not leave two findings, and downgrading to a
    clean result must not leave the old finding standing over a
    conclusion that replaced it.
    """
    org_id = await _signup(client, f"chg-{uuid.uuid4().hex[:8]}@example.com", "Chg Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework)
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    await db_session.commit()

    async def count() -> int:
        return int(
            (
                await db_session.execute(
                    select(func.count(AuditFinding.id)).where(
                        AuditFinding.audit_id == audit.id
                    )
                )
            ).scalar_one()
        )

    await record_decision(
        db_session, audit=audit, item=item, decision="major",
        note="No evidence of execution.", actor_user_id=None,
    )
    assert await count() == 1

    # Same conclusion again: the one finding is updated.
    await record_decision(
        db_session, audit=audit, item=item, decision="major",
        note="No evidence of execution.", actor_user_id=None,
    )
    assert await count() == 1

    # Downgraded to minor: still one finding, now medium.
    await record_decision(
        db_session, audit=audit, item=item, decision="minor",
        note="Partially evidenced after all.", actor_user_id=None,
    )
    assert await count() == 1
    finding = (
        await db_session.execute(
            select(AuditFinding).where(AuditFinding.audit_id == audit.id)
        )
    ).scalars().one()
    assert finding.severity == "medium"

    # Withdrawn entirely.
    await record_decision(
        db_session, audit=audit, item=item, decision="no_finding",
        note=None, actor_user_id=None,
    )
    assert await count() == 0
    assert item.finding_id is None


# --- §13 remediation is reused ------------------------------------------


@pytest.mark.anyio
async def test_an_existing_remediation_is_linked_not_duplicated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§13: one underlying problem, one piece of work.

    The requirement already has an open compliance gap with a task on it.
    An audit finding about the same requirement is a second description
    of that problem — opening a second task would put two rows on
    somebody's board for one job, which then get half-done each.
    """
    org_id = await _signup(client, f"dup-{uuid.uuid4().hex[:8]}@example.com", "Dup Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework)
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()

    existing_task = Task(
        organization_id=org_id,
        title="Document and perform quarterly AI risk review",
        module="compliance",
        status="open",
    )
    db_session.add(existing_task)
    await db_session.flush()
    db_session.add(
        ComplianceGap(
            organization_id=org_id,
            framework_id=framework.id,
            requirement_id=item.requirement_id,
            kind="evidence_missing",
            status="open",
            severity="high",
            summary="Missing AI risk review evidence.",
            task_id=existing_task.id,
        )
    )
    await db_session.commit()

    before = int(
        (
            await db_session.execute(
                select(func.count(Task.id)).where(Task.organization_id == org_id)
            )
        ).scalar_one()
    )

    result = await record_decision(
        db_session,
        audit=audit,
        item=item,
        decision="major",
        note="No evidence of periodic AI risk review.",
        actor_user_id=None,
    )
    await db_session.commit()

    assert result.task_reused is True
    assert result.task_id == existing_task.id
    assert result.finding.related_task_id == existing_task.id
    # And no second task was opened for the same problem.
    after = int(
        (
            await db_session.execute(
                select(func.count(Task.id)).where(Task.organization_id == org_id)
            )
        ).scalar_one()
    )
    assert after == before


@pytest.mark.anyio
async def test_a_finding_with_no_existing_gap_opens_its_own_work(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"new-{uuid.uuid4().hex[:8]}@example.com", "New Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework)
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    await db_session.commit()

    result = await record_decision(
        db_session, audit=audit, item=item, decision="critical",
        note="Nothing addresses this at all.", actor_user_id=None,
    )
    await db_session.commit()

    assert result.task_reused is False
    assert result.task_id is not None
    task = await db_session.get(Task, result.task_id)
    assert task.entity_type == "audit_finding"
    assert task.entity_id == str(result.finding.id)
    assert task.priority == "urgent"
    # The person doing the work is told what is missing, not just that
    # something is.
    assert item.reference_code in (task.description or "")


@pytest.mark.anyio
async def test_an_observation_does_not_open_remediation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Opening a task for every observation makes the board unreadable."""
    org_id = await _signup(client, f"obs-{uuid.uuid4().hex[:8]}@example.com", "Obs Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework)
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    await db_session.commit()

    result = await record_decision(
        db_session, audit=audit, item=item, decision="observation",
        note="Worth watching next cycle.", actor_user_id=None,
    )
    assert result.finding.severity == "low"
    assert result.task_id is None
    assert result.finding.status == "open"


# --- §11/§15/§16 fixing is not closing ---------------------------------


@pytest.mark.anyio
async def test_remediation_finishing_is_not_the_finding_closing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§11: the team does the work; the auditor decides whether it answers.

    Collapsing the two would let a task board close an audit finding —
    the person who did the work signing off on their own fix.
    """
    org_id = await _signup(client, f"ver-{uuid.uuid4().hex[:8]}@example.com", "Ver Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework, status="in_progress")
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    await db_session.commit()

    decision = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/decision",
        json={
            "decision": "major",
            "note": "No evidence of periodic AI risk review.",
        },
    )
    assert decision.status_code == 200, decision.text
    finding_id = decision.json()["finding"]["id"]

    # The team says it is done.
    ready = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/ready"
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "ready_for_verification"
    assert ready.json()["status_label"] == "Ready for verification"
    assert ready.json()["verified_at"] is None

    # A status update cannot produce a closure — that route has no
    # auditor and no note attached to it.
    sneaky = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/status",
        json={"status": "closed"},
    )
    assert sneaky.status_code == 422

    # And closing needs a reason.
    silent = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/verify",
        json={"note": "   "},
    )
    assert silent.status_code == 422

    closed = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/verify",
        json={
            "note": (
                "New quarterly AI risk review record demonstrates the process "
                "is now operating."
            )
        },
    )
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["status"] == "closed"
    # §16: who, when, and on what basis.
    assert body["verified_by"] is not None
    assert body["verified_at"] is not None
    assert "quarterly AI risk review" in body["verification_note"]

    # A retry is not a second closure.
    again = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/verify",
        json={"note": "Retried."},
    )
    assert again.status_code == 200
    assert again.json()["verification_note"] == body["verification_note"]

    events = list(
        (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.organization_id == org_id,
                    AuditEvent.action == "compliance.audit_finding.closed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1, "a retried verification is not a second closure"


@pytest.mark.anyio
async def test_an_auditor_can_send_it_back(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"reo-{uuid.uuid4().hex[:8]}@example.com", "Reo Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework, status="in_progress")
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    await db_session.commit()

    decision = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/decision",
        json={"decision": "critical", "note": "Nothing addresses this."},
    )
    finding_id = decision.json()["finding"]["id"]
    await client.post(f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/ready")

    reopened = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/reopen",
        json={"note": "The record covers one quarter, not a recurring process."},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "open"
    assert reopened.json()["verified_at"] is None


# --- §17/§18 completion -------------------------------------------------


@pytest.mark.anyio
async def test_an_audit_cannot_be_completed_over_open_work(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: an audit that finishes over an unverified critical finding
    says something untrue about the organization."""
    org_id = await _signup(client, f"comp-{uuid.uuid4().hex[:8]}@example.com", "Comp Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework, status="in_progress")
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    items = list(
        (
            await db_session.execute(
                select(AuditItem).where(AuditItem.audit_id == audit.id)
            )
        )
        .scalars()
        .all()
    )
    await db_session.commit()

    # Nothing reviewed yet.
    early = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "completed"}
    )
    assert early.status_code == 422
    assert "no auditor decision" in early.json()["error"]["message"]

    # Review everything, raising one critical finding.
    critical_item = items[0]
    decision = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{critical_item.id}/decision",
        json={"decision": "critical", "note": "Nothing addresses this at all."},
    )
    finding_id = decision.json()["finding"]["id"]
    for item in items[1:]:
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/decision",
            json={"decision": "no_finding"},
        )

    blocked = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "completed"}
    )
    assert blocked.status_code == 422
    assert "critical finding" in blocked.json()["error"]["message"]

    # Work done but unverified is still not resolved — that is exactly
    # the state completion must not paper over.
    await client.post(f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/ready")
    still = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "completed"}
    )
    assert still.status_code == 422
    assert "waiting on your verification" in still.json()["error"]["message"]

    await client.post(
        f"/api/v1/compliance/audits/{audit.id}/findings/{finding_id}/verify",
        json={"note": "New control and evidence reviewed; the gap is closed."},
    )
    done = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "completed"}
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    assert done.json()["completed_at"] is not None
    assert done.json()["started_at"] is not None


@pytest.mark.anyio
async def test_an_observation_does_not_block_completion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The rule, stated: minor findings and observations may stand open.

    An observation may simply stay open. A minor may too, but only once
    somebody owns the work — recording one now attaches remediation, so
    the normal flow satisfies that rather than dead-ending on it.
    """
    org_id = await _signup(client, f"obsc-{uuid.uuid4().hex[:8]}@example.com", "ObsC Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework, status="in_progress")
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    items = list(
        (
            await db_session.execute(
                select(AuditItem).where(AuditItem.audit_id == audit.id)
            )
        )
        .scalars()
        .all()
    )
    await db_session.commit()

    await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{items[0].id}/decision",
        json={"decision": "observation", "note": "Worth watching next cycle."},
    )
    await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{items[1].id}/decision",
        json={"decision": "minor", "note": "Documented late."},
    )
    for item in items[2:]:
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/decision",
            json={"decision": "no_finding"},
        )

    done = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}/status", json={"status": "completed"}
    )
    assert done.status_code == 200, done.text

    # §18: the summary the completion screen shows.
    detail = (await client.get(f"/api/v1/compliance/audits/{audit.id}")).json()
    progress = detail["progress"]
    assert progress["scoped"] == 18
    assert progress["reviewed"] == 18
    assert progress["percent_reviewed"] == 100
    assert progress["observations"] == 1
    assert progress["minor"] == 1
    assert progress["no_finding"] == 16
    assert progress["major"] == 0
    assert progress["critical"] == 0
    # Two findings still open, and neither blocks completion.
    assert progress["open_findings"] == 2
    assert detail["completion_blockers"] == []


@pytest.mark.anyio
async def test_progress_is_review_progress_not_readiness(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§21: 12 of 18 reviewed is a different number from 67% evidenced.

    A card showing one where the other belongs is worse than one showing
    neither, because both are plausible and only one is being asked for.
    """
    org_id = await _signup(client, f"prog-{uuid.uuid4().hex[:8]}@example.com", "Prog Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework, status="in_progress")
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    items = list(
        (
            await db_session.execute(
                select(AuditItem).where(AuditItem.audit_id == audit.id)
            )
        )
        .scalars()
        .all()
    )
    await db_session.commit()

    for item in items[:12]:
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/decision",
            json={"decision": "no_finding"},
        )

    listed = (await client.get("/api/v1/compliance/audits")).json()
    row = next(entry for entry in listed if entry["id"] == str(audit.id))
    assert row["progress"]["reviewed"] == 12
    assert row["progress"]["scoped"] == 18
    assert row["progress"]["unreviewed"] == 6
    assert row["progress"]["percent_reviewed"] == 67
    # §20: the card says where the engagement stands.
    assert row["status_label"] == "In progress"


# --- §24 what a completed audit keeps -----------------------------------


@pytest.mark.anyio
async def test_a_completed_audit_is_not_rewritten_by_later_changes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4/§24: the snapshot is what the auditor reviewed.

    Compliance state moves constantly. If the audit joined live to
    controls and evidence, today's uploads would silently rewrite last
    quarter's conclusions — which is the opposite of what an audit is for.
    """
    org_id = await _signup(client, f"hist-{uuid.uuid4().hex[:8]}@example.com", "Hist Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework, status="in_progress")
    await audit_workspace.prepare(db_session, audit=audit, actor_user_id=None)
    item = (
        await db_session.execute(
            select(AuditItem).where(AuditItem.audit_id == audit.id).limit(1)
        )
    ).scalars().one()
    item.control_title = "Operate an AI risk management process"
    item.prepared_status = "evidence_missing"
    item.prepared_why = "No evidence was on file when this audit was prepared."
    await db_session.flush()
    await db_session.commit()

    original_why = item.prepared_why
    original_status = item.prepared_status

    await client.post(
        f"/api/v1/compliance/audits/{audit.id}/items/{item.id}/decision",
        json={"decision": "major", "note": "No evidence of periodic execution."},
    )

    # The organization fixes it: a control appears and gets mapped.
    control = Control(
        organization_id=org_id,
        title="Operate an AI risk management process",
        status="implemented",
    )
    db_session.add(control)
    await db_session.flush()
    db_session.add(
        ControlMapping(control_id=control.id, requirement_id=item.requirement_id)
    )
    await db_session.commit()

    # Re-preparing refreshes undecided rows and leaves this one alone.
    await client.post(f"/api/v1/compliance/audits/{audit.id}/prepare")
    await db_session.refresh(item)

    assert item.prepared_why == original_why
    assert item.prepared_status == original_status
    assert item.decision == "major"


@pytest.mark.anyio
async def test_an_audit_opened_without_a_framework_can_be_scoped_later(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Audits exist that are a title and nothing else.

    Making somebody abandon the record and open a second audit for the
    same engagement is a worse answer than letting them attach the
    framework they meant.
    """
    org_id = await _signup(client, f"late-{uuid.uuid4().hex[:8]}@example.com", "Late Org")
    framework = await _framework(db_session)
    await db_session.commit()

    created = await client.post(
        "/api/v1/compliance/audits",
        json={"title": "ISO 42001 Internal Audit", "auditor_name": "Zach Warren"},
    )
    assert created.status_code == 201, created.text
    audit_id = created.json()["id"]
    assert created.json()["progress"]["scoped"] == 0

    scoped = await client.patch(
        f"/api/v1/compliance/audits/{audit_id}",
        json={
            "framework_id": str(framework.id),
            "scope": "AI governance controls and evidence",
        },
    )
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["progress"]["scoped"] == 18
    assert scoped.json()["scope"] == "AI governance controls and evidence"
    assert scoped.json()["prepared_at"] is not None


@pytest.mark.anyio
async def test_a_completed_audit_cannot_be_re_scoped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Its findings were reached against the scope it had."""
    org_id = await _signup(client, f"frz-{uuid.uuid4().hex[:8]}@example.com", "Frz Org")
    framework = await _framework(db_session)
    audit = await _audit(db_session, org_id, framework=framework, status="completed")
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/compliance/audits/{audit.id}",
        json={"scope": "Something else entirely"},
    )
    assert response.status_code == 409
    assert "cannot be re-scoped" in response.json()["error"]["message"]
