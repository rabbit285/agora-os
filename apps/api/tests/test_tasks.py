from __future__ import annotations

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import File
from app.main import app


async def _signup(client: AsyncClient, email: str, org_name: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Task Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


async def test_create_task_records_creator_entity_link_and_checklist(
    client: AsyncClient,
) -> None:
    user_id, _ = await _signup(client, "task1@example.com", "Task Org 1")

    response = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Investigate finding",
            "entity_type": "audit_finding",
            "entity_id": str(uuid.uuid4()),
            "checklist": [{"text": "Confirm root cause", "done": False}],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created_by"] == str(user_id)
    assert body["entity_type"] == "audit_finding"
    assert body["checklist"] == [{"text": "Confirm root cause", "done": False}]

    fetched = await client.get(f"/api/v1/tasks/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


async def test_update_task_checklist_toggles_an_item(client: AsyncClient) -> None:
    await _signup(client, "task2@example.com", "Task Org 2")
    created = await client.post(
        "/api/v1/tasks",
        json={"title": "Review policy", "checklist": [{"text": "Draft v1", "done": False}]},
    )
    task_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"checklist": [{"text": "Draft v1", "done": True}]},
    )
    assert updated.status_code == 200
    assert updated.json()["checklist"] == [{"text": "Draft v1", "done": True}]


async def test_task_comments_can_be_added_and_listed(client: AsyncClient) -> None:
    user_id, _ = await _signup(client, "task3@example.com", "Task Org 3")
    created = await client.post("/api/v1/tasks", json={"title": "Ship the report"})
    task_id = created.json()["id"]

    comment = await client.post(f"/api/v1/tasks/{task_id}/comments", json={"body": "On it."})
    assert comment.status_code == 201, comment.text
    assert comment.json()["author_id"] == str(user_id)

    listing = await client.get(f"/api/v1/tasks/{task_id}/comments")
    assert listing.status_code == 200
    assert [c["body"] for c in listing.json()] == ["On it."]


async def test_task_evidence_attaches_an_uploaded_file(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "task4@example.com", "Task Org 4")
    created = await client.post("/api/v1/tasks", json={"title": "Attach proof"})
    task_id = created.json()["id"]

    file_record = File(
        organization_id=org_id,
        storage_key=f"org/{org_id}/{uuid.uuid4()}/proof.pdf",
        original_filename="proof.pdf",
        content_type="application/pdf",
        size_bytes=100,
        uploaded_by=user_id,
    )
    db_session.add(file_record)
    await db_session.flush()
    await db_session.commit()

    attach = await client.post(
        f"/api/v1/tasks/{task_id}/evidence", json={"file_id": str(file_record.id)}
    )
    assert attach.status_code == 201, attach.text
    assert attach.json()["file_id"] == str(file_record.id)

    listing = await client.get(f"/api/v1/tasks/{task_id}/evidence")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


async def test_task_evidence_rejects_a_file_from_another_org(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "task5a@example.com", "Task Org 5a")
    created = await client.post("/api/v1/tasks", json={"title": "Attach proof"})
    task_id = created.json()["id"]

    other_org_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    stray_file = File(
        organization_id=other_org_id,
        storage_key=f"org/{other_org_id}/{uuid.uuid4()}/stray.pdf",
        original_filename="stray.pdf",
        content_type="application/pdf",
        size_bytes=100,
        uploaded_by=other_user_id,
    )
    db_session.add(stray_file)
    await db_session.flush()
    await db_session.commit()

    attach = await client.post(
        f"/api/v1/tasks/{task_id}/evidence", json={"file_id": str(stray_file.id)}
    )
    assert attach.status_code == 404


async def test_task_activity_reflects_real_mutations(client: AsyncClient) -> None:
    await _signup(client, "task6@example.com", "Task Org 6")
    created = await client.post("/api/v1/tasks", json={"title": "Track me"})
    task_id = created.json()["id"]

    await client.patch(f"/api/v1/tasks/{task_id}", json={"status": "in_progress"})
    await client.post(f"/api/v1/tasks/{task_id}/comments", json={"body": "note"})

    activity = await client.get(f"/api/v1/tasks/{task_id}/activity")
    assert activity.status_code == 200
    actions = [event["action"] for event in activity.json()]
    assert actions == ["core.task.created", "core.task.status_changed", "core.task.commented"]


async def test_task_from_another_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "task7a@example.com", "Task Org 7a")
    created = await client.post("/api/v1/tasks", json={"title": "Org 7a's task"})
    task_id = created.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    await _signup(other_client, "task7b@example.com", "Task Org 7b")

    for path in (
        f"/api/v1/tasks/{task_id}",
        f"/api/v1/tasks/{task_id}/comments",
        f"/api/v1/tasks/{task_id}/evidence",
        f"/api/v1/tasks/{task_id}/activity",
    ):
        response = await other_client.get(path)
        assert response.status_code == 404, path
    await other_client.aclose()


async def test_approval_out_includes_module_and_ai_generated(client: AsyncClient) -> None:
    """A high-risk AI system registration creates a real Approval — proves
    the new module/ai_generated/due_at fields round-trip through the API,
    not just the ORM."""
    await _signup(client, "task8@example.com", "Task Org 8")
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Resume Screener",
            "vendor": "Acme AI",
            "purpose": "Screens job applicants",
            "risk_classification": "high",
        },
    )

    approvals = await client.get("/api/v1/approvals")
    assert approvals.status_code == 200
    matching = [a for a in approvals.json() if a["module"] == "compliance"]
    assert len(matching) == 1
    assert matching[0]["ai_generated"] is False
