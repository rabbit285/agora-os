from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership, MembershipRole
from app.core.rbac import ensure_system_roles, get_system_role
from app.identity.models import User
from app.identity.service import create_session
from app.security import hash_password


async def _create_member_with_role(
    db_session: AsyncSession, *, organization_id: str, email: str, role_key: str
) -> str:
    """Creates a user with the given system role in the given org and
    returns a raw session token (bypassing the HTTP signup flow, since
    Phase 1 has no invite endpoint yet — see docs/ROUTES_AND_SCREENS.md)."""
    org_uuid = uuid.UUID(str(organization_id))
    await ensure_system_roles(db_session)
    user = User(email=email, hashed_password=hash_password("irrelevant-password-123"))
    db_session.add(user)
    await db_session.flush()

    membership = Membership(organization_id=org_uuid, user_id=user.id, status="active")
    db_session.add(membership)
    await db_session.flush()

    role = await get_system_role(db_session, role_key)
    db_session.add(MembershipRole(membership_id=membership.id, role_id=role.id))

    session = await create_session(
        db_session, user=user, organization_id=org_uuid, ip_address=None, user_agent=None
    )
    await db_session.commit()
    return session.raw_token  # type: ignore[attr-defined]


async def test_read_only_role_cannot_create_tasks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "admin@example.com",
            "password": "correct-horse-battery",
            "full_name": "Admin",
            "organization_name": "RBAC Test Org",
        },
    )
    organization_id = signup.json()["organization"]["id"]
    await client.post("/api/v1/auth/logout")

    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="read-only@example.com",
        role_key="read_only",
    )
    client.cookies.set("agora_session", token)

    # Read-only access (no specific permission required) still works.
    listing = await client.get("/api/v1/tasks")
    assert listing.status_code == 200

    # Mutating access requires core.tasks.manage, which "read_only" is
    # deliberately seeded with zero permissions and therefore lacks.
    creation = await client.post("/api/v1/tasks", json={"title": "Should be forbidden"})
    assert creation.status_code == 403


async def test_employee_role_can_create_tasks_and_use_knowledge_and_copilot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Employee is the org-wide default role (spec §54): it should be able
    to manage its own tasks and use the cross-cutting Knowledge/Copilot
    capabilities every role gets, even though it holds none of the
    module-specific "manage" permissions (Sales/Security/Compliance/etc.)."""
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "admin3@example.com",
            "password": "correct-horse-battery",
            "full_name": "Admin",
            "organization_name": "Employee RBAC Org",
        },
    )
    organization_id = signup.json()["organization"]["id"]
    await client.post("/api/v1/auth/logout")

    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="employee2@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)

    creation = await client.post("/api/v1/tasks", json={"title": "Employees can do this"})
    assert creation.status_code == 201

    # Still has no module-specific manage permission. Uses a compliance
    # endpoint rather than the sales one this originally asserted against:
    # sales was withdrawn from the product, and a 404 from a missing route
    # would pass for a denial without proving anything about RBAC.
    forbidden = await client.post(
        "/api/v1/compliance/controls", json={"title": "Should be forbidden"}
    )
    assert forbidden.status_code == 403


async def test_read_only_role_cannot_upload_documents_or_ask_copilot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "admin4@example.com",
            "password": "correct-horse-battery",
            "full_name": "Admin",
            "organization_name": "Knowledge RBAC Org",
        },
    )
    organization_id = signup.json()["organization"]["id"]
    await client.post("/api/v1/auth/logout")

    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="read-only2@example.com",
        role_key="read_only",
    )
    client.cookies.set("agora_session", token)

    kb_creation = await client.post("/api/v1/knowledge/knowledge-bases", json={"name": "KB"})
    assert kb_creation.status_code == 403

    ask = await client.post("/api/v1/ai/copilot/ask", json={"prompt": "What is our policy?"})
    assert ask.status_code == 403


async def test_employee_role_can_upload_documents_and_ask_copilot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "admin5@example.com",
            "password": "correct-horse-battery",
            "full_name": "Admin",
            "organization_name": "Knowledge RBAC Org 2",
        },
    )
    organization_id = signup.json()["organization"]["id"]
    await client.post("/api/v1/auth/logout")

    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="employee3@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)

    kb_creation = await client.post("/api/v1/knowledge/knowledge-bases", json={"name": "KB"})
    assert kb_creation.status_code == 201

    ask = await client.post("/api/v1/ai/copilot/ask", json={"prompt": "What is our policy?"})
    assert ask.status_code == 200


async def test_org_admin_can_create_and_decide(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "founder2@example.com",
            "password": "correct-horse-battery",
            "full_name": "Founder",
            "organization_name": "Admin Org",
        },
    )
    creation = await client.post("/api/v1/tasks", json={"title": "Admin can do this"})
    assert creation.status_code == 201
