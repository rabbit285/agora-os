"""The executive view.

Written for someone accountable for compliance who does not work in it
daily. These tests are mostly about the two ways that reader gets
misled: a number with nothing behind it, and a panel that claims work
which did not happen.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.dashboard import ACTIVITY_LABELS, _next_actions
from app.compliance.dashboard import FrameworkStatus
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
            "full_name": "Dashboard Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


def _framework(percent: float = 50.0) -> FrameworkStatus:
    return FrameworkStatus(
        framework_id=uuid.uuid4(),
        key="gdpr",
        name="GDPR",
        readiness_percent=percent,
        explanation="",
        open_gap_count=0,
    )


# --- What to do next --------------------------------------------------


def test_a_company_that_has_declared_nothing_is_asked_that_first() -> None:
    """With no facts we cannot say what applies, so everything downstream
    is guesswork."""
    actions = _next_actions(
        frameworks=[],
        proposals_awaiting=0,
        unscreened_systems=0,
        overdue_actions=0,
        critical_gaps=0,
        facts_declared=False,
    )
    assert actions
    assert "Tell Veyntra about your company" in actions[0].title


def test_reviewing_evidence_is_offered_before_chasing_gaps() -> None:
    """Approving evidence can close a gap without any remediation, so it
    is the cheaper move and belongs first."""
    actions = _next_actions(
        frameworks=[_framework()],
        proposals_awaiting=5,
        unscreened_systems=0,
        overdue_actions=0,
        critical_gaps=9,
        facts_declared=True,
    )
    titles = [action.title for action in actions]
    assert any("Review 5 evidence mapping" in title for title in titles)
    # Chasing gaps is suppressed entirely while there is evidence waiting,
    # rather than listed below it — two competing "do this next" items is
    # how a next-action panel becomes a backlog.
    assert not any("Close" in title for title in titles)


def test_gaps_are_offered_once_there_is_no_evidence_waiting() -> None:
    actions = _next_actions(
        frameworks=[_framework()],
        proposals_awaiting=0,
        unscreened_systems=0,
        overdue_actions=0,
        critical_gaps=4,
        facts_declared=True,
    )
    assert any("Close 4 high-severity gap" in action.title for action in actions)


def test_every_next_action_links_somewhere() -> None:
    actions = _next_actions(
        frameworks=[],
        proposals_awaiting=3,
        unscreened_systems=2,
        overdue_actions=1,
        critical_gaps=0,
        facts_declared=True,
    )
    assert actions
    for action in actions:
        assert action.href.startswith("/")
        assert action.priority in {"high", "medium", "low"}


def test_a_settled_organization_is_told_nothing_rather_than_padded() -> None:
    actions = _next_actions(
        frameworks=[_framework(100.0)],
        proposals_awaiting=0,
        unscreened_systems=0,
        overdue_actions=0,
        critical_gaps=0,
        facts_declared=True,
    )
    assert actions == []


def test_activity_labels_are_readable_without_a_glossary() -> None:
    """The panel is read by someone who does not work in compliance
    daily. An audit action name is not a sentence."""
    for label in ACTIVITY_LABELS.values():
        assert "{s}" in label or not label.endswith("s")
        assert "compliance." not in label
        assert "_" not in label


# --- The endpoint -----------------------------------------------------


async def test_a_new_organization_gets_an_honest_zero(client: AsyncClient) -> None:
    """Not a bare 0%, which reads as failure. It has to say there is
    nothing to measure against yet."""
    await _signup(client, "dash-new@example.com")
    body = (await client.get("/api/v1/compliance/dashboard")).json()

    assert body["readiness_percent"] == 0.0
    assert "No framework adopted yet" in body["readiness_explanation"]
    assert body["frameworks"] == []


async def test_readiness_is_weighted_by_requirement_count(client: AsyncClient) -> None:
    """A two-requirement framework at 100% must not pull the overall
    figure as hard as a twenty-five-requirement one."""
    await _signup(client, "dash-weighted@example.com")
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    soc2 = next(f for f in frameworks if f["key"] == "soc2")
    for framework in (gdpr, soc2):
        await client.put(
            f"/api/v1/compliance/frameworks/{framework['id']}/activation",
            json={"active": True},
        )

    body = (await client.get("/api/v1/compliance/dashboard")).json()
    assert len(body["frameworks"]) == 2
    assert "weighted by their" in body["readiness_explanation"]
    # 25 GDPR requirements + 2 SOC 2 requirements.
    assert "27 requirements" in body["readiness_explanation"]


async def test_recent_activity_is_counted_not_narrated(client: AsyncClient) -> None:
    """Read from the audit trail, so the panel can never claim work that
    did not happen."""
    await _signup(client, "dash-activity@example.com")
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    await client.put(
        f"/api/v1/compliance/frameworks/{gdpr['id']}/activation", json={"active": True}
    )

    body = (await client.get("/api/v1/compliance/dashboard")).json()
    labels = {line["label"] for line in body["recent_activity"]}
    assert any("adopted" in label for label in labels)


async def test_the_dashboard_never_claims_compliance(client: AsyncClient) -> None:
    await _signup(client, "dash-language@example.com")
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    await client.put(
        f"/api/v1/compliance/frameworks/{gdpr['id']}/activation", json={"active": True}
    )

    body = (await client.get("/api/v1/compliance/dashboard")).json()
    text = str(body).lower()
    for forbidden in ("you are compliant", "fully compliant", "non-compliant", "violation"):
        assert forbidden not in text


async def test_the_dashboard_is_tenant_scoped(client: AsyncClient) -> None:
    await _signup(client, "dash-tenant-a@example.com")
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    await client.put(
        f"/api/v1/compliance/frameworks/{gdpr['id']}/activation", json={"active": True}
    )
    await client.post("/api/v1/auth/logout")

    await _signup(client, "dash-tenant-b@example.com")
    body = (await client.get("/api/v1/compliance/dashboard")).json()
    assert body["frameworks"] == []
    assert body["ai_system_count"] == 0
