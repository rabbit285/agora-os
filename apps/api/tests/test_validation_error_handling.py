"""Regression test for a cross-cutting bug found while adding Onboarding's
goals-step validator (spec §68): Pydantic v2 includes the raw exception
instance in `ctx` for any `@field_validator` that raises a plain
`ValueError` with a dynamic message. `app.main`'s `RequestValidationError`
handler passed `exc.errors()` straight into `json.dumps`, which can't
serialize that — every custom validator in this codebase (not just the
new Onboarding one; `WorkflowCreate.trigger_type`/`steps` already had this
same shape) returned a 500 instead of the intended 422, previously
untested. Fixed by running `exc.errors()` through FastAPI's own
`jsonable_encoder` first.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Validation Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_custom_field_validator_error_returns_422_not_500(client: AsyncClient) -> None:
    """app.automation.schemas.WorkflowCreate.trigger_type — a
    pre-existing custom @field_validator that raises ValueError, never
    previously exercised by an invalid value in any test."""
    await _signup(client, "validation1@example.com", "Validation Org 1")
    response = await client.post(
        "/api/v1/automation/workflows",
        json={"name": "Test Workflow", "trigger_type": "not_a_real_trigger"},
    )
    assert response.status_code == 422, response.text
    assert "Unsupported trigger_type" in response.text
