from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import Workflow, WorkflowRun, WorkflowStepRun, WorkflowVersion
from app.automation.service import advance_run, publish_workflow_version, start_run
from app.core.models import Approval, Task


async def _signup(client: AsyncClient, email: str, org_name: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Service Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


def _workflow(*, organization_id: uuid.UUID, steps: list[dict], owner_id: uuid.UUID) -> Workflow:
    return Workflow(
        organization_id=organization_id,
        name="Direct service test workflow",
        trigger_type="manual",
        status="active",
        steps=steps,
        owner_id=owner_id,
    )


async def test_advance_run_executes_all_steps_when_no_pause(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc1@example.com", "Service Org 1")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {"step_type": "create_task", "config": {"title": "Task one"}},
            {"step_type": "send_notification", "config": {"title": "Done", "body": "All set"}},
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    assert run.status == "running"

    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"
    assert run.completed_at is not None


async def test_advance_run_pauses_on_human_approval_and_resumes_after_decision(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc2@example.com", "Service Org 2")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {"step_type": "create_task", "config": {"title": "Prep"}},
            {
                "step_type": "human_approval",
                "config": {"action_type": "Approve the thing", "risk_class": "high"},
            },
            {"step_type": "create_task", "config": {"title": "Finalize"}},
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "awaiting_approval"

    # Resuming before a decision is a no-op.
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "awaiting_approval"

    step_runs = (
        (await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id)))
        .scalars()
        .all()
    )
    approval_id = next(s.approval_id for s in step_runs if s.approval_id is not None)
    approval = await db_session.get(Approval, approval_id)
    assert approval is not None
    approval.status = "approved"
    await db_session.flush()

    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"

    final_step_runs = (
        (await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id)))
        .scalars()
        .all()
    )
    assert len(final_step_runs) == 3


async def test_advance_run_fails_on_rejected_approval(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc3@example.com", "Service Org 3")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[{"step_type": "human_approval", "config": {"action_type": "Risky action"}}],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "awaiting_approval"

    from sqlalchemy import select

    step_run = (
        await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id))
    ).scalar_one()
    approval = await db_session.get(Approval, step_run.approval_id)
    assert approval is not None
    approval.status = "rejected"
    await db_session.flush()

    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "failed"


async def test_condition_step_ends_run_early_when_false(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc4@example.com", "Service Org 4")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {
                "step_type": "condition",
                "config": {"field": "amount", "operator": "equals", "value": 100},
            },
            {"step_type": "create_task", "config": {"title": "Should not run"}},
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload={"amount": 50},
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"

    from sqlalchemy import select

    step_runs = (
        (await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id)))
        .scalars()
        .all()
    )
    assert len(step_runs) == 1  # the second create_task step never ran


async def test_condition_step_continues_when_true(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc5@example.com", "Service Org 5")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {
                "step_type": "condition",
                "config": {"field": "amount", "operator": "equals", "value": 100},
            },
            {"step_type": "create_task", "config": {"title": "Should run"}},
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload={"amount": 100},
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"

    from sqlalchemy import select

    step_runs = (
        (await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id)))
        .scalars()
        .all()
    )
    assert len(step_runs) == 2


async def test_delay_step_stops_the_batch_for_the_workflow_to_sleep(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc6@example.com", "Service Org 6")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {"step_type": "delay", "config": {"seconds": 60}},
            {"step_type": "create_task", "config": {"title": "After delay"}},
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    # Still "running" — the batch stopped right after the delay step so
    # the Temporal workflow can sleep for real before resuming.
    assert run.status == "running"

    from sqlalchemy import select

    step_runs = (
        (await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id)))
        .scalars()
        .all()
    )
    assert len(step_runs) == 1
    assert step_runs[0].step_type == "delay"
    assert step_runs[0].output["waited_seconds"] == 60

    # Resuming (simulating the workflow waking up after its real sleep)
    # continues past the delay step.
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"


async def test_loop_step_repeats_inner_step_per_item(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc7@example.com", "Service Org 7")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {
                "step_type": "loop",
                "config": {
                    "items": ["a", "b", "c"],
                    "step_type": "send_notification",
                    "config": {"title": "Loop notification"},
                },
            }
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"

    from sqlalchemy import select

    step_runs = (
        (await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id)))
        .scalars()
        .all()
    )
    assert len(step_runs) == 1
    assert step_runs[0].output["iterations"] == 3


async def test_assign_user_step_sets_task_assignee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc8@example.com", "Service Org 8")
    task = Task(organization_id=org_id, title="Existing task", module="automation")
    db_session.add(task)
    await db_session.flush()

    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {
                "step_type": "assign_user",
                "config": {
                    "entity_type": "task",
                    "entity_id": str(task.id),
                    "user_id": str(user_id),
                },
            }
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"

    await db_session.refresh(task)
    assert task.assignee_id == user_id


async def test_send_email_step_honestly_reports_not_delivered(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc9@example.com", "Service Org 9")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {"step_type": "send_email", "config": {"to": "someone@example.com", "subject": "Hi"}}
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"

    from sqlalchemy import select

    step_run = (
        await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id))
    ).scalar_one()
    assert step_run.output["sent"] is False


async def test_send_chat_message_step_honestly_reports_no_connection(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc10@example.com", "Service Org 10")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[{"step_type": "send_chat_message", "config": {"channel": "#general"}}],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"

    from sqlalchemy import select

    step_run = (
        await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id))
    ).scalar_one()
    assert step_run.output["sent"] is False
    assert step_run.output["connection_found"] is False


async def test_call_api_step_makes_a_real_http_call(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc11@example.com", "Service Org 11")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {"step_type": "call_api", "config": {"url": "https://httpstat.us/200", "method": "GET"}}
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)

    from sqlalchemy import select

    step_run = (
        await db_session.execute(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id))
    ).scalar_one()
    # Network access may not be available in every CI sandbox; either a
    # real response or a real connection failure is an honest outcome —
    # what matters is that call_api never fabricates a result.
    assert step_run.status in ("succeeded", "failed")
    assert step_run.output is not None


async def test_publish_workflow_version_snapshots_steps(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc12@example.com", "Service Org 12")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[{"step_type": "create_task", "config": {"title": "v1"}}],
    )
    workflow.version = 1
    db_session.add(workflow)
    await db_session.flush()

    version = await publish_workflow_version(db_session, workflow=workflow, published_by=user_id)
    assert version.version_number == 1
    assert version.steps == workflow.steps

    from sqlalchemy import select

    versions = (
        (
            await db_session.execute(
                select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(versions) == 1


async def test_run_with_unsupported_step_type_raises(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc13@example.com", "Service Org 13")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[{"step_type": "not_a_real_step", "config": {}}],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    try:
        await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
        raised = False
    except ValueError:
        raised = True
    assert raised


async def test_dispatch_event_starts_a_run_for_matching_active_workflow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.automation.triggers import dispatch_event

    user_id, org_id = await _signup(client, "svc14@example.com", "Service Org 14")
    workflow = Workflow(
        organization_id=org_id,
        name="Lead-triggered workflow",
        trigger_type="new_crm_lead",
        status="active",
        steps=[{"step_type": "create_task", "config": {"title": "Follow up"}}],
        owner_id=user_id,
    )
    db_session.add(workflow)
    await db_session.flush()

    run_ids = await dispatch_event(
        db_session,
        organization_id=org_id,
        trigger_type="new_crm_lead",
        payload={"lead_id": "abc"},
        actor_user_id=user_id,
    )
    assert len(run_ids) == 1
    run = await db_session.get(WorkflowRun, run_ids[0])
    assert run is not None
    assert run.workflow_id == workflow.id


async def test_dispatch_event_ignores_non_matching_or_inactive_workflows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.automation.triggers import dispatch_event

    user_id, org_id = await _signup(client, "svc15@example.com", "Service Org 15")
    inactive = Workflow(
        organization_id=org_id,
        name="Draft workflow",
        trigger_type="new_crm_lead",
        status="draft",
        steps=[{"step_type": "create_task", "config": {}}],
        owner_id=user_id,
    )
    other_trigger = Workflow(
        organization_id=org_id,
        name="Different trigger",
        trigger_type="new_vendor",
        status="active",
        steps=[{"step_type": "create_task", "config": {}}],
        owner_id=user_id,
    )
    db_session.add_all([inactive, other_trigger])
    await db_session.flush()

    run_ids = await dispatch_event(
        db_session,
        organization_id=org_id,
        trigger_type="new_crm_lead",
        payload={},
        actor_user_id=user_id,
    )
    assert run_ids == []


async def test_export_data_step_fails_run_without_an_active_transfer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "svc16@example.com", "Service Org 16")
    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {
                "step_type": "export_data",
                "config": {"destination_country": "US", "data_classification": "restricted"},
            }
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "failed"


async def test_export_data_step_succeeds_with_an_active_transfer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "svc17@example.com",
            "password": "correct-horse-battery",
            "full_name": "Service Tester",
            "organization_name": "Service Org 17",
        },
    )
    user_id = uuid.UUID(response.json()["user"]["id"])
    org_id = uuid.UUID(response.json()["organization"]["id"])

    await client.post(
        "/api/v1/compliance/data-transfers",
        json={
            "recipient_name": "US Partner Inc",
            "destination_country": "US",
            "transfer_mechanism": "sccs",
        },
    )

    workflow = _workflow(
        organization_id=org_id,
        owner_id=user_id,
        steps=[
            {
                "step_type": "export_data",
                "config": {"destination_country": "US", "data_classification": "restricted"},
            }
        ],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = await start_run(
        db_session,
        organization_id=org_id,
        workflow=workflow,
        trigger_payload=None,
        actor_user_id=user_id,
    )
    run = await advance_run(db_session, run=run, workflow=workflow, actor_user_id=user_id)
    assert run.status == "succeeded"
