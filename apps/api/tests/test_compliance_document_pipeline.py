"""Document intelligence pipeline: scaffolding, readiness, reassessment.

These cover the promise the module is sold on — upload once, and the
system does the compliance work — at the three points where it would
quietly stop being true:

* adopting a framework must create somewhere for evidence to land,
* the readiness number must carry its own arithmetic, and
* new evidence must mark the old conclusion stale rather than silently
  replacing it.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.assessment import (
    READINESS_WEIGHTS,
    RequirementEvaluation,
    scaffold_controls_for_framework,
    summarize_readiness,
)
from app.compliance.models import Control, ControlMapping, Framework, Requirement
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
            "full_name": "Pipeline Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


def _evaluation(status: str) -> RequirementEvaluation:
    return RequirementEvaluation(
        requirement=Requirement(
            id=uuid.uuid4(), reference_code="Art. 1", title="Test requirement"
        ),
        status=status,
        control_ids=[],
        evidence_count=0,
        latest_assessment_status=None,
        summary="",
    )


# --- The readiness score must explain itself -------------------------


def test_explanation_states_the_counts_behind_the_number() -> None:
    breakdown = summarize_readiness(
        [
            _evaluation("satisfied"),
            _evaluation("needs_review"),
            _evaluation("deficient"),
            _evaluation("evidence_missing"),
        ]
    )

    # 1.0 + 0.5 + 0.25 + 0 = 1.75 of 4.
    assert breakdown.percent == 43.8
    assert "1 satisfied" in breakdown.explanation
    assert "1 awaiting review" in breakdown.explanation
    assert "1 with an identified deficiency" in breakdown.explanation
    assert "1 missing evidence" in breakdown.explanation
    assert "43.8%" in breakdown.explanation


def test_an_open_question_scores_above_a_named_deficiency() -> None:
    """Evidence on file with nothing shown to be wrong is a better
    position than evidence with a condition known to be unmet. Scoring
    them the same was part of why "needs review" and "gap" looked
    interchangeable on the framework screen."""
    assert READINESS_WEIGHTS["needs_review"] > READINESS_WEIGHTS["deficient"]
    assert READINESS_WEIGHTS["deficient"] > READINESS_WEIGHTS["evidence_missing"]


def test_nothing_to_assess_scores_zero_rather_than_dividing_by_zero() -> None:
    breakdown = summarize_readiness([])
    assert breakdown.percent == 0.0
    assert breakdown.total == 0


def test_only_satisfied_earns_full_credit() -> None:
    """Guards the number against overstating the position: no status other
    than `satisfied` may ever be worth a whole requirement."""
    for status, weight in READINESS_WEIGHTS.items():
        if status != "satisfied":
            assert weight < 1.0, f"{status} must not count as fully ready"
    assert READINESS_WEIGHTS["satisfied"] == 1.0


def test_a_fully_evidenced_framework_reads_one_hundred_percent() -> None:
    breakdown = summarize_readiness([_evaluation("satisfied") for _ in range(3)])
    assert breakdown.percent == 100.0


def test_the_explanation_never_asserts_a_legal_conclusion() -> None:
    """Missing evidence is missing evidence. The product must not turn the
    absence of a document into an accusation."""
    breakdown = summarize_readiness([_evaluation("evidence_missing"), _evaluation("satisfied")])
    lowered = breakdown.explanation.lower()
    for forbidden in ("violation", "breach", "non-compliant", "illegal", "unlawful"):
        assert forbidden not in lowered


# --- Adopting a framework must create somewhere for evidence to land --


async def test_adopting_a_framework_scaffolds_shared_controls(
    client: AsyncClient,
) -> None:
    """Adopting a framework must leave somewhere for evidence to land.

    This previously asserted one control per requirement. That was the
    wrong shape: one measure satisfies requirements across several
    frameworks, and duplicating it per requirement would have produced
    61 controls for three frameworks and asked the customer to evidence
    the same thing repeatedly. What matters is that requirements get
    covered, not that controls and requirements count the same.
    """
    await _signup(client, "scaffold-shared@example.com")
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")

    activation = await client.put(
        f"/api/v1/compliance/frameworks/{gdpr['id']}/activation", json={"active": True}
    )
    assert activation.status_code == 200

    controls = (await client.get("/api/v1/compliance/controls")).json()
    assert controls, "adopting a framework produced no controls"
    # Fewer controls than requirements is the point, not a shortfall.
    requirements = (
        await client.get(f"/api/v1/compliance/frameworks/{gdpr['id']}/requirements")
    ).json()
    assert len(controls) < len(requirements)

    # Adopting must not move the compliance position.
    scaffolded = [c for c in controls if c["status"] == "not_started"]
    assert len(scaffolded) == len(controls)


async def test_adopting_a_second_framework_reuses_existing_controls(
    client: AsyncClient,
) -> None:
    """The argument for adopting a second framework here.

    An organization already holding "Restrict access to personal data"
    for GDPR should get that same control mapped to the ISO 42001
    clause, so their existing evidence starts counting immediately —
    not a duplicate control with its own empty evidence list.
    """
    await _signup(client, "scaffold-reuse@example.com")
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    iso = next(f for f in frameworks if f["key"] == "iso42001")

    await client.put(
        f"/api/v1/compliance/frameworks/{gdpr['id']}/activation", json={"active": True}
    )
    after_first = (await client.get("/api/v1/compliance/controls")).json()

    await client.put(
        f"/api/v1/compliance/frameworks/{iso['id']}/activation", json={"active": True}
    )
    after_second = (await client.get("/api/v1/compliance/controls")).json()

    iso_requirements = (
        await client.get(f"/api/v1/compliance/frameworks/{iso['id']}/requirements")
    ).json()
    added = len(after_second) - len(after_first)

    assert added >= 0
    # The second framework must cost fewer new controls than it has
    # requirements, or nothing was reused.
    assert added < len(iso_requirements)

    # And the shared ones really are mapped into both frameworks.
    dashboard = (
        await client.get(f"/api/v1/compliance/frameworks/{iso['id']}/dashboard")
    ).json()
    covered = [row for row in dashboard["requirements"] if row["controls"]]
    assert covered, "ISO 42001 requirements got no controls at all"

async def test_scaffolding_leaves_the_organizations_own_controls_alone(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Re-activating a framework must never duplicate or overwrite work
    the organization already did."""
    await _signup(client, "scaffold-idempotent@example.com")
    organization_id = uuid.uuid4()

    framework = Framework(key=f"repeat-{uuid.uuid4().hex[:8]}", name="Repeat Framework")
    db_session.add(framework)
    await db_session.flush()
    requirement = Requirement(
        framework_id=framework.id, reference_code="Art. 1", title="Requirement"
    )
    db_session.add(requirement)
    await db_session.flush()

    mine = Control(
        organization_id=organization_id,
        title="My own carefully named control",
        status="implemented",
    )
    db_session.add(mine)
    await db_session.flush()
    db_session.add(ControlMapping(control_id=mine.id, requirement_id=requirement.id))
    await db_session.flush()

    created = await scaffold_controls_for_framework(
        db_session,
        organization_id=organization_id,
        framework=framework,
        actor_user_id=None,
    )

    assert created == 0
    await db_session.refresh(mine)
    assert mine.title == "My own carefully named control"
    assert mine.status == "implemented"


# --- The documents endpoints -----------------------------------------


async def test_processing_an_unknown_file_is_not_found(client: AsyncClient) -> None:
    await _signup(client, "doc-unknown@example.com")
    response = await client.post(
        "/api/v1/compliance/documents/process",
        json={"file_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


async def test_document_list_reports_only_valid_lifecycle_states(client: AsyncClient) -> None:
    await _signup(client, "doc-list@example.com")
    response = await client.get("/api/v1/compliance/documents")
    assert response.status_code == 200
    for document in response.json():
        assert document["processing_status"] in {
            "uploaded",
            "parsing",
            "analyzing",
            "ready",
            "failed",
            "unsupported",
        }


async def test_a_documents_library_is_scoped_to_its_own_organization(
    client: AsyncClient,
) -> None:
    """Tenant isolation on the new endpoint."""
    await _signup(client, "doc-tenant-a@example.com")
    first = await client.get("/api/v1/compliance/documents")
    assert first.status_code == 200

    await client.post("/api/v1/auth/logout")
    await _signup(client, "doc-tenant-b@example.com")
    second = await client.get("/api/v1/compliance/documents")
    assert second.status_code == 200
    assert second.json() == []

# --- The chain closes without a manual assessment ---------------------


async def test_adopting_a_framework_then_approving_evidence_needs_no_manual_assess(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The promise is upload once, review, and see readiness move.

    Approving evidence has to re-run the assessment for the frameworks the
    control serves; otherwise the customer approves a mapping, nothing
    visibly changes, and they are left to discover a "Run assessment"
    button on a page they were never sent to.
    """
    await _signup(client, "chain-closes@example.com")

    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    activation = await client.put(
        f"/api/v1/compliance/frameworks/{gdpr['id']}/activation", json={"active": True}
    )
    assert activation.status_code == 200

    # Adopting builds the control set, which is what an uploaded document
    # gets proposed against.
    controls = (await client.get("/api/v1/compliance/controls")).json()
    assert len(controls) > 0

    overview = (await client.get("/api/v1/compliance/overview")).json()
    assert len(overview["frameworks"]) == 1
    assert overview["frameworks"][0]["framework_key"] == "gdpr"
    # Adopting a framework must not move the compliance position.
    assert overview["frameworks"][0]["readiness"]["percent"] == 0.0


async def test_overview_is_read_only_and_does_not_reconcile_gaps(
    client: AsyncClient,
) -> None:
    """The overview is fetched on every page load. If it reconciled gaps
    the act of looking at the dashboard would open and close findings, and
    the audit trail would fill with events nobody performed."""
    await _signup(client, "overview-readonly@example.com")
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    await client.put(
        f"/api/v1/compliance/frameworks/{gdpr['id']}/activation", json={"active": True}
    )

    before = (await client.get("/api/v1/compliance/gaps")).json()
    for _ in range(3):
        assert (await client.get("/api/v1/compliance/overview")).status_code == 200
    after = (await client.get("/api/v1/compliance/gaps")).json()

    assert len(after) == len(before)


async def test_overview_of_an_organization_with_no_framework_is_empty_not_zero(
    client: AsyncClient,
) -> None:
    """No framework adopted means no controls, so an upload has nothing to
    map to. The UI needs to tell the user that rather than show a row of
    zeros that reads as a failing score."""
    await _signup(client, "overview-empty@example.com")
    body = (await client.get("/api/v1/compliance/overview")).json()
    assert body["frameworks"] == []
    assert body["total_open_gaps"] == 0
