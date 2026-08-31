"""Per-system AI governance: completeness, actions, readiness.

The engine is deterministic on purpose — the output is a checklist the
customer will be held to, and it has to be the same checklist every time
they look. These tests are mostly about what it refuses to say: an
undocumented oversight arrangement is reported as absent from the record,
never as a violation, and nothing here concludes that a system is lawful.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.ai_system_governance import (
    DOCUMENTATION_FIELDS,
    applicable_regulations,
    documentation_state,
    required_actions,
)
from app.compliance.models import AISystem
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
            "full_name": "AI Governance Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


def _system(**overrides: object) -> AISystem:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "organization_id": uuid.uuid4(),
        "name": "Customer Support AI",
        "purpose": "Answer customer questions from the knowledge base.",
        "risk_classification": "limited",
        "deployment_status": "production",
        "is_external": True,
        "personal_data_processed": True,
        "sensitive_data_processed": False,
        "automated_decision_making": False,
        "third_party_vendors": [],
        "internal_users": [],
        "affected_users": [],
        "processed_data": [],
    }
    defaults.update(overrides)
    return AISystem(**defaults)  # type: ignore[arg-type]


# --- Documentation completeness --------------------------------------


def test_an_empty_entry_reports_what_is_missing_not_a_failure() -> None:
    percent, missing = documentation_state(_system())
    assert percent < 100
    assert missing
    # Labels, not attribute names — the customer reads these.
    assert all(" " in label for label in missing)


def test_a_complete_entry_reports_full_documentation() -> None:
    filled = {attribute: "recorded" for attribute, _ in DOCUMENTATION_FIELDS}
    filled["business_owner_id"] = uuid.uuid4()
    filled["technical_owner_id"] = uuid.uuid4()
    filled["affected_users"] = ["Customers"]
    filled["processed_data"] = [{"name": "Email", "classification": "confidential"}]
    percent, missing = documentation_state(_system(**filled))
    assert percent == 100
    assert missing == []


# --- Which regulations reach one system ------------------------------


def test_a_system_touching_no_personal_data_does_not_list_gdpr() -> None:
    """Otherwise the field is meaningless — every card would list GDPR
    simply because the organization is subject to it."""
    system = _system(personal_data_processed=False, automated_decision_making=False)
    assert applicable_regulations(system) == ["EU AI Act"]


def test_automated_decisions_bring_gdpr_into_scope_for_the_system() -> None:
    system = _system(personal_data_processed=True, automated_decision_making=True)
    assert "GDPR" in applicable_regulations(system)


# --- Required actions -------------------------------------------------


def test_an_unscreened_system_is_asked_to_be_screened() -> None:
    actions = required_actions(
        _system(), missing_documentation=[], has_current_screening=False, open_incident_count=0
    )
    assert any("Screen this system" in action.title for action in actions)


def test_high_risk_without_oversight_is_raised_as_high_priority() -> None:
    actions = required_actions(
        _system(risk_classification="high", human_oversight=None),
        missing_documentation=[],
        has_current_screening=True,
        open_incident_count=0,
    )
    oversight = next(a for a in actions if "oversees" in a.title)
    assert oversight.priority == "high"
    assert "Art. 14" in oversight.basis


def test_automated_decisions_on_personal_data_ask_for_article_22_safeguards() -> None:
    actions = required_actions(
        _system(automated_decision_making=True, personal_data_processed=True),
        missing_documentation=[],
        has_current_screening=True,
        open_incident_count=0,
    )
    assert any("Art. 22" in action.basis for action in actions)


def test_every_action_names_the_obligation_behind_it() -> None:
    """An action nobody can trace to a requirement is busywork."""
    actions = required_actions(
        _system(risk_classification="high", sensitive_data_processed=True),
        missing_documentation=["A business owner"],
        has_current_screening=False,
        open_incident_count=2,
    )
    assert actions
    assert all(action.basis for action in actions)


def test_a_development_system_is_prioritised_below_a_live_one() -> None:
    """A gap on something still in development is a planning item. The
    same gap in production is live exposure."""
    in_dev = required_actions(
        _system(deployment_status="development"),
        missing_documentation=[],
        has_current_screening=False,
        open_incident_count=0,
    )
    live = required_actions(
        _system(deployment_status="production"),
        missing_documentation=[],
        has_current_screening=False,
        open_incident_count=0,
    )
    assert in_dev[0].priority == "medium"
    assert live[0].priority == "high"


def test_no_action_asserts_the_organization_is_in_breach() -> None:
    actions = required_actions(
        _system(risk_classification="high", sensitive_data_processed=True),
        missing_documentation=["A business owner"],
        has_current_screening=False,
        open_incident_count=1,
    )
    for action in actions:
        text = f"{action.title} {action.detail}".lower()
        for forbidden in ("violation", "breach of", "non-compliant", "illegal", "unlawful"):
            assert forbidden not in text


# --- The endpoints ----------------------------------------------------


async def test_governance_overview_is_empty_for_a_new_organization(
    client: AsyncClient,
) -> None:
    await _signup(client, "aigov-empty@example.com")
    body = (await client.get("/api/v1/compliance/ai-systems/governance")).json()
    assert body["total_systems"] == 0
    assert body["systems"] == []


async def test_a_registered_system_appears_with_actions_and_an_explanation(
    client: AsyncClient,
) -> None:
    await _signup(client, "aigov-one@example.com")
    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Customer Support AI",
            "purpose": "Answer customer questions.",
            "risk_classification": "limited",
        },
    )
    assert created.status_code == 201, created.text

    body = (await client.get("/api/v1/compliance/ai-systems/governance")).json()
    assert body["total_systems"] == 1
    system = body["systems"][0]
    assert system["required_actions"], "a bare inventory entry should have outstanding work"
    # A readiness figure never appears without the arithmetic behind it.
    assert system["explanation"]
    assert str(system["readiness_percent"]) in system["explanation"]


async def test_governance_facts_can_be_recorded_and_change_the_actions(
    client: AsyncClient,
) -> None:
    await _signup(client, "aigov-update@example.com")
    system_id = (
        await client.post(
            "/api/v1/compliance/ai-systems",
            json={
                "name": "Resume Screener",
                "purpose": "Rank applicants.",
                "risk_classification": "high",
            },
        )
    ).json()["id"]

    before = (await client.get("/api/v1/compliance/ai-systems/governance")).json()["systems"][0]
    assert any("oversees" in action["title"] for action in before["required_actions"])

    updated = await client.patch(
        f"/api/v1/compliance/ai-systems/{system_id}/governance",
        json={
            "human_oversight": "A recruiter reviews every ranking before it is acted on.",
            "deployment_status": "pilot",
        },
    )
    assert updated.status_code == 200, updated.text

    after = (await client.get("/api/v1/compliance/ai-systems/governance")).json()["systems"][0]
    assert not any("oversees" in action["title"] for action in after["required_actions"])


async def test_governance_is_tenant_scoped(client: AsyncClient) -> None:
    await _signup(client, "aigov-tenant-a@example.com")
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Tenant A System", "purpose": "Something."},
    )
    await client.post("/api/v1/auth/logout")

    await _signup(client, "aigov-tenant-b@example.com")
    body = (await client.get("/api/v1/compliance/ai-systems/governance")).json()
    assert body["total_systems"] == 0


async def test_updating_another_organizations_system_is_not_found(
    client: AsyncClient,
) -> None:
    await _signup(client, "aigov-cross-a@example.com")
    system_id = (
        await client.post(
            "/api/v1/compliance/ai-systems",
            json={"name": "Private System", "purpose": "Something."},
        )
    ).json()["id"]
    await client.post("/api/v1/auth/logout")

    await _signup(client, "aigov-cross-b@example.com")
    response = await client.patch(
        f"/api/v1/compliance/ai-systems/{system_id}/governance",
        json={"deployment_status": "production"},
    )
    assert response.status_code == 404
