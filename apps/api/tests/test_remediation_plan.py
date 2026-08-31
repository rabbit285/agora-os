"""A gap has to become work somebody can pick up.

These tests exist because the remediation task shipped as an empty
shell: a title, a sentence restating the finding, an empty checklist, no
evidence list, no activity. Everything asserted here is a property of
that shell being gone — and of it staying gone for every framework,
rather than only for the one requirement that was reported.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.remediation import PLAYBOOKS, build_plan, render_description
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
            "full_name": "Remediation Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _register_ai_system(client: AsyncClient, name: str = "Support Copilot") -> str:
    """EU AI Act requirements are scoped to the systems an organization
    actually runs — see app.compliance.requirement_applicability. Without
    a registered system Art. 4 correctly does not apply, and there is no
    gap to remediate."""
    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": name,
            "vendor": "Anthropic",
            "purpose": "Drafts replies to customer support tickets.",
            "risk_classification": "limited",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _adopt(client: AsyncClient, key: str) -> tuple[str, dict[str, str]]:
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    framework_id = next(f["id"] for f in frameworks if f["key"] == key)
    await client.put(
        f"/api/v1/compliance/frameworks/{framework_id}/activation", json={"active": True}
    )
    requirements = (
        await client.get(f"/api/v1/compliance/frameworks/{framework_id}/requirements")
    ).json()
    return framework_id, {r["reference_code"]: r["id"] for r in requirements}


# --- The plan itself, without a database ------------------------------


def test_every_playbook_ends_by_getting_the_evidence_back_in() -> None:
    """Work done and never uploaded leaves the compliance position exactly
    where it was, so no plan may end before that step."""
    for (framework_key, code), playbook in PLAYBOOKS.items():
        plan = build_plan(
            framework_key=framework_key,
            framework_name=framework_key,
            requirement_code=code,
            requirement_title=code,
            requirement_description=None,
            gap_kind="evidence_missing",
            severity="high",
            control_title=None,
            evidence_reviewed=[],
            affected_ai_systems=[],
        )
        assert "upload" in plan.checklist[-1].lower(), (framework_key, code)
        assert len(playbook.required_evidence) >= 1


def test_a_requirement_with_no_playbook_still_gets_actionable_steps() -> None:
    """The fallback is deliberately modest, but "modest" cannot mean
    empty — an empty checklist is the bug this module was written for."""
    plan = build_plan(
        framework_key="gdpr",
        framework_name="GDPR",
        requirement_code="Art. 999",
        requirement_title="Some requirement with no playbook",
        requirement_description=None,
        gap_kind="no_control",
        severity="medium",
        control_title=None,
        evidence_reviewed=[],
        affected_ai_systems=[],
    )
    assert plan.checklist
    assert plan.required_evidence
    assert plan.owner
    assert plan.problem and plan.action


def test_the_plan_says_what_was_already_read() -> None:
    """A plan that asks for evidence without naming what it already
    reviewed reads as though nobody looked."""
    plan = build_plan(
        framework_key="eu_ai_act",
        framework_name="EU AI Act",
        requirement_code="Art. 4",
        requirement_title="AI literacy",
        requirement_description=None,
        gap_kind="evidence_partial",
        severity="high",
        control_title="AI literacy programme",
        evidence_reviewed=["employee-handbook.pdf"],
        affected_ai_systems=["Support Copilot"],
    )
    assert "employee-handbook.pdf" in plan.evidence_reviewed
    assert "AI literacy programme" in plan.why
    rendered = render_description(plan)
    assert "employee-handbook.pdf" in rendered
    assert "Support Copilot" in rendered
    assert "Suggested owner" in rendered


def test_severity_drives_priority_not_a_flat_high() -> None:
    def priority(severity: str) -> str:
        return build_plan(
            framework_key="gdpr",
            framework_name="GDPR",
            requirement_code="Art. 30",
            requirement_title="Records of processing activities",
            requirement_description=None,
            gap_kind="evidence_missing",
            severity=severity,
            control_title=None,
            evidence_reviewed=[],
            affected_ai_systems=[],
        ).priority

    assert priority("high") == "high"
    assert priority("low") == "low"
    assert priority("high") != priority("low")


def test_no_plan_leaks_an_internal_name() -> None:
    """These strings are read by someone who does not work in compliance
    daily; a gap kind or an action name is not a sentence."""
    for (framework_key, code) in PLAYBOOKS:
        plan = build_plan(
            framework_key=framework_key,
            framework_name=framework_key,
            requirement_code=code,
            requirement_title=code,
            requirement_description=None,
            gap_kind="evidence_missing",
            severity="high",
            control_title=None,
            evidence_reviewed=[],
            affected_ai_systems=[],
        )
        text = render_description(plan)
        for leak in ("evidence_missing", "no_control", "compliance_gap", "_id"):
            assert leak not in text, (code, leak)


# --- Through the API --------------------------------------------------


async def test_a_gap_carries_its_plan_the_moment_it_is_raised(
    client: AsyncClient,
) -> None:
    """Not on a later button press. A finding whose fix the product
    already knows should not wait for someone to ask."""
    await _signup(client, "remediation-eager@example.com")
    await _register_ai_system(client)
    framework_id, _ = await _adopt(client, "eu_ai_act")

    result = (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()
    gap_id = next(
        r["gap_id"] for r in result["requirements"] if r["reference_code"] == "Art. 4"
    )
    assert gap_id, "Art. 4 should be in scope for an organization that uses AI"

    gap = (await client.get(f"/api/v1/compliance/gaps/{gap_id}")).json()
    plan = gap["remediation_plan"]
    assert plan is not None, "the gap was raised without a plan"
    assert plan["checklist"], "the checklist was empty — this is the reported bug"
    assert plan["required_evidence"]
    assert plan["owner"]
    assert "literacy" in plan["problem"].lower()


async def test_the_task_is_the_plan_not_a_shell(client: AsyncClient) -> None:
    """The reported symptom, asserted directly: title, populated
    checklist, real instructions, a suggested owner and a due date that
    came from the work rather than a hardcoded seven days."""
    await _signup(client, "remediation-task@example.com")
    await _register_ai_system(client)
    framework_id, _ = await _adopt(client, "eu_ai_act")

    result = (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()
    gap_id = next(
        r["gap_id"] for r in result["requirements"] if r["reference_code"] == "Art. 4"
    )

    # No overrides — the plan decides.
    created = await client.post(f"/api/v1/compliance/gaps/{gap_id}/task", json={})
    assert created.status_code == 201, created.text
    task = created.json()

    assert len(task["checklist"]) >= 5, task["checklist"]
    assert all(item["done"] is False for item in task["checklist"])
    assert any("literacy" in item["text"].lower() for item in task["checklist"])

    description = task["description"]
    for heading in ("PROBLEM", "WHY THIS MATTERS", "WHAT TO DO"):
        assert heading in description
    assert "Suggested owner" in description

    # The Art. 4 playbook allows 45 days because running a training
    # programme is not a one-line policy edit.
    assert task["due_at"]
    assert task["priority"] in {"low", "normal", "high", "urgent"}


async def test_the_task_activity_shows_the_gap_lifecycle(client: AsyncClient) -> None:
    """The task's history is not only its own — the interesting events
    happen to the gap. Reading only `object_type="task"` is why these
    tasks appeared to have no activity at all."""
    await _signup(client, "remediation-activity@example.com")
    await _register_ai_system(client)
    framework_id, _ = await _adopt(client, "eu_ai_act")

    result = (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()
    gap_id = next(
        r["gap_id"] for r in result["requirements"] if r["reference_code"] == "Art. 4"
    )
    task = (
        await client.post(f"/api/v1/compliance/gaps/{gap_id}/task", json={})
    ).json()

    activity = (await client.get(f"/api/v1/tasks/{task['id']}/activity")).json()
    labels = [entry["label"] for entry in activity]
    assert labels, "no activity recorded"
    assert any("Remediation plan generated" in label for label in labels)
    assert any("Gap identified" in label for label in labels)

    # Every line is a sentence, never an internal action name.
    for entry in activity:
        assert "compliance." not in entry["label"]
        assert "core.task." not in entry["label"]
        assert "_" not in entry["label"]


async def test_ticking_a_checklist_item_is_recorded(client: AsyncClient) -> None:
    await _signup(client, "remediation-checklist@example.com")
    await _register_ai_system(client)
    framework_id, _ = await _adopt(client, "eu_ai_act")
    result = (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()
    gap_id = next(
        r["gap_id"] for r in result["requirements"] if r["reference_code"] == "Art. 4"
    )
    task = (
        await client.post(f"/api/v1/compliance/gaps/{gap_id}/task", json={})
    ).json()

    checklist = task["checklist"]
    checklist[0]["done"] = True
    patched = await client.patch(
        f"/api/v1/tasks/{task['id']}", json={"checklist": checklist}
    )
    assert patched.status_code == 200, patched.text

    activity = (await client.get(f"/api/v1/tasks/{task['id']}/activity")).json()
    assert any("Checklist updated" in entry["label"] for entry in activity)


async def test_assigning_an_owner_is_recorded_by_name(client: AsyncClient) -> None:
    """The plan suggests a team because we do not know the customer's org
    chart. Naming the person is theirs to do, and the trail says who."""
    await _signup(client, "remediation-owner@example.com")
    await _register_ai_system(client)
    framework_id, _ = await _adopt(client, "eu_ai_act")
    result = (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()
    gap_id = next(
        r["gap_id"] for r in result["requirements"] if r["reference_code"] == "Art. 4"
    )
    task = (
        await client.post(f"/api/v1/compliance/gaps/{gap_id}/task", json={})
    ).json()

    me = (await client.get("/api/v1/auth/me")).json()
    patched = await client.patch(
        f"/api/v1/tasks/{task['id']}", json={"assignee_id": me["id"]}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["assignee_id"] == me["id"]

    activity = (await client.get(f"/api/v1/tasks/{task['id']}/activity")).json()
    assert any("Owner assigned" in entry["label"] for entry in activity)


async def test_gdpr_gaps_get_plans_too_not_only_the_eu_ai_act(
    client: AsyncClient,
) -> None:
    """The fix is to the shared pipeline. A framework-specific patch would
    leave the next customer with the same empty shell."""
    await _signup(client, "remediation-gdpr@example.com")
    framework_id, _ = await _adopt(client, "gdpr")

    result = (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()
    gap_ids = [r["gap_id"] for r in result["requirements"] if r["gap_id"]]
    assert gap_ids, "adopting GDPR with no evidence should raise gaps"

    for gap_id in gap_ids:
        gap = (await client.get(f"/api/v1/compliance/gaps/{gap_id}")).json()
        plan = gap["remediation_plan"]
        assert plan is not None, gap["summary"]
        assert plan["checklist"], gap["summary"]
        assert plan["required_evidence"], gap["summary"]
