"""Three dimensions, one truth.

A control badge read "Needs review · 100%". Three different questions were
collapsed into it:

- **Evidence coverage** — how much supporting evidence exists (100%).
- **AI assessment** — what Veyntra derived (needs review).
- **Human decision** — what a person concluded (nothing yet).

The percentage sat inside the status badge, so a measurement looked like
part of a state. And the human decision was carried alongside without ever
becoming the answer, so a control still read "Needs review" after somebody
had reviewed and passed it — telling them their decision did nothing.

These tests hold the three apart and pin the rule that joins them: the
effective status is the human verdict where one exists, the derived
assessment otherwise, and the derived one is never overwritten.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.control_assessment import (
    ASSESSMENT_LABELS,
    HUMAN_VERDICTS,
    ControlAssessmentView,
    effective_status,
    requires_human_review,
)
from app.compliance.evidence_ai import (
    DocumentAnalysis,
    ProposedMapping,
    suggest_evidence_mappings,
)
from app.compliance.models import Control
from app.core.models import File, Membership
from app.seed import _ensure_compliance_catalog

MONITORING_POLICY = """ACME AI SAAS - AI MONITORING POLICY

Section 1 Monitoring
Product teams monitor material failures, user feedback and incidents for
every AI system in production, and review the metrics each month.
"""


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


class _StubGateway:
    def __init__(self, mappings: list[ProposedMapping]) -> None:
        self._mappings = mappings

    async def generate_structured(self, db, *, organization_id, requested_by, request, schema):  # type: ignore[no-untyped-def]
        return DocumentAnalysis(
            document_type="Monitoring Policy",
            document_domain="AI Governance",
            mappings=self._mappings,
        )


def _view(ai: str, human: str | None, coverage: int = 0) -> ControlAssessmentView:
    return ControlAssessmentView(
        control_id=uuid.uuid4(),
        status=ai,
        confidence=coverage,
        why="",
        missing=None,
        recorded_status=human,
    )


# --- The rule ----------------------------------------------------------


def test_a_human_decision_becomes_the_effective_status() -> None:
    """Leaving the headline at "Needs review" after somebody reviewed it
    tells them their decision did nothing."""
    assert effective_status("needs_review", "passed") == "passed"
    assert effective_status("evidenced", "failed") == "failed"
    assert effective_status("needs_review", None) == "needs_review"


def test_recording_not_assessed_is_not_a_decision() -> None:
    """"I have not assessed this" must not override what Veyntra
    derived — it is the absence of a verdict, not a verdict."""
    assert HUMAN_VERDICTS.get("not_assessed") is None
    view = _view("needs_review", "not_assessed", coverage=100)
    assert view.human_status is None
    assert view.effective_status == "needs_review"
    assert view.review_required is True


def test_the_ai_assessment_survives_a_human_decision() -> None:
    """"A person disagreed with the automated assessment" is exactly what
    an auditor wants to see."""
    view = _view("needs_review", "pass", coverage=100)
    assert view.effective_status == "passed"
    assert view.ai_status == "needs_review"
    assert view.ai_label == "Needs review"
    assert view.human_status == "passed"


def test_the_review_queue_closes_once_somebody_decides() -> None:
    assert requires_human_review("needs_review", None) is True
    assert requires_human_review("needs_review", "passed") is False
    assert requires_human_review("needs_review", "failed") is False
    # Only `needs_review` ever asks for a person.
    assert requires_human_review("evidenced", None) is False


def test_status_and_coverage_are_independent() -> None:
    """The bug in one line: 100% coverage did not mean the control was
    settled, and the badge implied it did."""
    settled = _view("evidenced", None, coverage=100)
    unsettled = _view("needs_review", None, coverage=100)
    assert settled.confidence == unsettled.confidence == 100
    assert settled.effective_status != unsettled.effective_status
    assert settled.review_required is False
    assert unsettled.review_required is True


def test_every_status_has_a_human_readable_label() -> None:
    """No screen may ever render `partially_evidenced`."""
    for status in (
        "not_applicable",
        "no_evidence",
        "evidence_insufficient",
        "needs_review",
        "partially_evidenced",
        "evidenced",
        "passed",
        "failed",
        "partially_implemented",
    ):
        label = ASSESSMENT_LABELS[status]
        assert "_" not in label, status
        assert label[0].isupper(), status


# --- The cases from the report ----------------------------------------


def test_case_a_needs_review_at_full_coverage() -> None:
    view = _view("needs_review", None, coverage=100)
    assert view.effective_status == "needs_review"
    assert view.label == "Needs review"
    assert view.confidence == 100
    assert view.review_required is True


def test_case_b_human_passes_at_full_coverage() -> None:
    view = _view("needs_review", "pass", coverage=100)
    assert view.effective_status == "passed"
    assert view.label == "Passed"
    assert view.confidence == 100
    assert view.ai_status == "needs_review"
    assert view.review_required is False


def test_case_c_human_fails() -> None:
    view = _view("needs_review", "fail", coverage=100)
    assert view.effective_status == "failed"
    assert view.label == "Failed"
    assert view.ai_status == "needs_review"
    assert view.review_required is False


def test_case_d_partial_coverage() -> None:
    view = _view("partially_evidenced", None, coverage=50)
    assert view.effective_status == "partially_evidenced"
    assert view.label == "Partially evidenced"
    assert view.confidence == 50


def test_case_e_evidence_that_proves_nothing() -> None:
    """Never "Partially evidenced · 0%"."""
    view = _view("evidence_insufficient", None, coverage=0)
    assert view.effective_status == "evidence_insufficient"
    assert view.label == "Evidence insufficient"
    assert view.confidence == 0


def test_case_f_nothing_applicable() -> None:
    view = _view("not_applicable", None, coverage=0)
    assert view.effective_status == "not_applicable"
    assert view.label == "Not applicable"
    assert view.review_required is False


# --- Through the API --------------------------------------------------


async def _signup(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"effective-{uuid.uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery",
            "full_name": "Acme Compliance Lead",
            "organization_name": f"Acme Effective {uuid.uuid4().hex[:6]}",
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


async def _control_by_title(client: AsyncClient, title: str) -> dict:
    controls = (await client.get("/api/v1/compliance/controls?limit=200")).json()
    match = next((c for c in controls if c["title"] == title), None)
    assert match is not None, f"no control titled {title!r}"
    return match


async def test_the_acceptance_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    """`Monitor AI systems in production` from needs-review to passed,
    checked on both screens at every step."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    await client.put(
        "/api/v1/compliance/company-facts",
        json={
            "operates_in_eu": True,
            "sells_to_eu_customers": True,
            "processes_personal_data": True,
            "uses_third_party_ai": True,
            "builds_ai_features": True,
            "sells_to_enterprise": True,
        },
    )
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Credit Scoring Engine",
            "vendor": "In-house",
            "purpose": "Scores applicants.",
            "risk_classification": "high",
        },
    )
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    for key in ("eu_ai_act", "iso42001"):
        framework_id = next(f["id"] for f in frameworks if f["key"] == key)
        await client.put(
            f"/api/v1/compliance/frameworks/{framework_id}/activation",
            json={"active": True},
        )

    title = "Monitor AI systems in production"

    # Evidence, cited against one requirement, so coverage is real.
    upload = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "monitoring-policy.txt",
            "content_type": "text/plain",
            "size_bytes": len(MONITORING_POLICY),
            "classification": "confidential",
        },
    )
    file_record = await db_session.get(File, uuid.UUID(upload.json()["file_id"]))
    assert file_record is not None

    controls = list(
        (
            await db_session.execute(
                select(Control)
                .where(Control.organization_id == organization_id)
                .order_by(Control.created_at, Control.id)
            )
        )
        .scalars()
        .all()
    )
    index = next(i for i, c in enumerate(controls, start=1) if c.title == title)
    detail_before = await _control_by_title(client, title)
    codes = (
        await client.get(f"/api/v1/compliance/controls/{detail_before['id']}")
    ).json()["assessment"]["requirements"]
    applicable = [line["reference_code"] for line in codes if line["applicability"] != "not_applicable"]

    await suggest_evidence_mappings(
        db_session,
        organization_id=organization_id,
        file_record=file_record,
        file_bytes=MONITORING_POLICY.encode(),
        actor_user_id=None,
        gateway=_StubGateway(
            [
                ProposedMapping(
                    control_index=index,
                    section_index=1,
                    confidence=0.95,
                    rationale="Section 1 sets out the monitoring obligation.",
                    evidence_type="policy_statement",
                    requirement_code=code,
                    quoted_passage="Product teams monitor material failures, user feedback and incidents",
                )
                for code in applicable
            ]
        ),
    )
    await db_session.commit()

    # --- Step 1: the list, before any human review --------------------
    listed = await _control_by_title(client, title)
    assert listed["coverage_percent"] == 100, listed
    assert listed["assessment_status"] == "needs_review"
    assert listed["assessment_label"] == "Needs review"
    assert listed["ai_assessment_status"] == "needs_review"
    assert listed["human_assessment_status"] is None
    assert listed["review_required"] is True

    control_id = listed["id"]

    # --- Step 2: a person records Passed ------------------------------
    recorded = await client.post(
        f"/api/v1/compliance/controls/{control_id}/assessments",
        json={"status": "pass", "notes": "Metrics reviewed monthly, evidence checked."},
    )
    assert recorded.status_code == 201, recorded.text

    # --- Step 3: the list now says Passed -----------------------------
    listed = await _control_by_title(client, title)
    assert listed["assessment_status"] == "passed"
    assert listed["assessment_label"] == "Passed"
    assert listed["coverage_percent"] == 100
    # The derived assessment is preserved, not replaced.
    assert listed["ai_assessment_status"] == "needs_review"
    assert listed["human_assessment_status"] == "passed"
    assert listed["human_reviewed_at"]
    assert listed["review_required"] is False

    # --- Step 4: the detail agrees, and shows all three ----------------
    detail = (await client.get(f"/api/v1/compliance/controls/{control_id}")).json()
    assessment = detail["assessment"]
    assert assessment["effective_status"] == "passed"
    assert assessment["label"] == "Passed"
    assert assessment["ai_status"] == "needs_review"
    assert assessment["ai_label"] == "Needs review"
    assert assessment["human_status"] == "passed"
    assert assessment["human_label"] == "Passed"
    assert assessment["confidence"] == 100
    assert assessment["review_required"] is False
    # The list and the detail must never disagree.
    assert detail["assessment_status"] == listed["assessment_status"]
    assert detail["coverage_percent"] == listed["coverage_percent"]

    # --- Step 5: the audit trail records who decided -------------------
    me = (await client.get("/api/v1/auth/me")).json()
    events = (await client.get(f"/api/v1/audit-events?object_id={control_id}")).json()
    assessed = [e for e in events if e["action"] == "compliance.control.assessed"]
    assert assessed, events
    assert assessed[0]["actor_user_id"] == me["id"]


async def test_no_control_reports_a_status_it_cannot_justify(
    client: AsyncClient,
) -> None:
    """Across every control: the effective status is either the human
    verdict or the derived one, and never something else."""
    await _signup(client)
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    for key in ("gdpr", "eu_ai_act"):
        framework_id = next(f["id"] for f in frameworks if f["key"] == key)
        await client.put(
            f"/api/v1/compliance/frameworks/{framework_id}/activation",
            json={"active": True},
        )

    controls = (await client.get("/api/v1/compliance/controls?limit=200")).json()
    assert len(controls) > 5

    for control in controls:
        expected = control["human_assessment_status"] or control["ai_assessment_status"]
        assert control["assessment_status"] == expected, control["title"]
        assert control["assessment_label"] == ASSESSMENT_LABELS[expected]
        # A control only asks for review when nobody has decided.
        if control["human_assessment_status"]:
            assert control["review_required"] is False
