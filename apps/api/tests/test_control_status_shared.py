"""One control, one status, on every screen.

The reported failure: `Monitor AI systems in production` read "Partially
evidenced · 33% · missing Art. 15 and Art. 72" on its own page and "not
started" in the controls list. Two derivations of one fact — the list
rendered the stored `Control.status` workflow column, the detail page
called the derived assessment service — so which answer a customer saw
depended on which screen they opened.

Every test here asserts through the API, and the ones that matter assert
the *list* and the *detail* agree. A unit test of the service alone would
have passed throughout the period the bug existed.

The percentage is the second half of it: it divided documents by *mapped*
requirements, so one policy on a three-requirement control read 33%
whether it answered one obligation or all three, and a requirement that
did not bind the organization at all still sat in the denominator.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

Section 2 Accuracy
Accuracy, robustness and cybersecurity of each system are measured
against a documented baseline before release and after every change.
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


async def _signup(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"ctlstatus-{uuid.uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery",
            "full_name": "Acme Compliance Lead",
            "organization_name": f"Acme Controls {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _declare(client: AsyncClient, **overrides: object) -> None:
    """Declare company facts. Without a profile row every scoping rule is
    answered from an all-false default, which is `needs_review`, not
    `not_applicable`."""
    payload = {
        "operates_in_eu": True,
        "sells_to_eu_customers": True,
        "processes_personal_data": True,
        "uses_third_party_ai": True,
        "builds_ai_features": False,
        "sells_to_enterprise": True,
    }
    payload.update(overrides)  # type: ignore[arg-type]
    response = await client.put("/api/v1/compliance/company-facts", json=payload)
    assert response.status_code == 200, response.text


async def _register_system(
    client: AsyncClient, name: str, risk: str, deployment: str = "development"
) -> str:
    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": name,
            "vendor": "OpenAI",
            "purpose": "Supports an internal workflow.",
            "risk_classification": risk,
        },
    )
    assert response.status_code == 201, response.text
    system_id = str(response.json()["id"])
    if deployment != "development":
        updated = await client.patch(
            f"/api/v1/compliance/ai-systems/{system_id}/governance",
            json={"deployment_status": deployment},
        )
        assert updated.status_code == 200, updated.text
    return system_id


async def _organization_id(client: AsyncClient, db: AsyncSession) -> uuid.UUID:
    me = (await client.get("/api/v1/auth/me")).json()
    return (
        await db.execute(
            select(Membership.organization_id).where(
                Membership.user_id == uuid.UUID(me["id"])
            )
        )
    ).scalar_one()


async def _adopt(client: AsyncClient, key: str) -> str:
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    framework_id = next(f["id"] for f in frameworks if f["key"] == key)
    await client.put(
        f"/api/v1/compliance/frameworks/{framework_id}/activation", json={"active": True}
    )
    return str(framework_id)


async def _control_by_title(client: AsyncClient, title: str) -> dict:
    controls = (await client.get("/api/v1/compliance/controls?limit=200")).json()
    match = next((c for c in controls if c["title"] == title), None)
    assert match is not None, f"no control titled {title!r}"
    return match


async def _detail(client: AsyncClient, control_id: str) -> dict:
    response = await client.get(f"/api/v1/compliance/controls/{control_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def _upload(client: AsyncClient, db: AsyncSession, filename: str, body: str) -> File:
    response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": filename,
            "content_type": "text/plain",
            "size_bytes": len(body),
            "classification": "confidential",
        },
    )
    assert response.status_code == 200, response.text
    record = await db.get(File, uuid.UUID(response.json()["file_id"]))
    assert record is not None
    return record


async def _control_index(db: AsyncSession, organization_id: uuid.UUID, title: str) -> int:
    controls = list(
        (
            await db.execute(
                select(Control)
                .where(Control.organization_id == organization_id)
                .order_by(Control.created_at, Control.id)
            )
        )
        .scalars()
        .all()
    )
    for index, control in enumerate(controls, start=1):
        if control.title == title:
            return index
    raise AssertionError(f"No control titled {title!r}")


async def _map_evidence(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    control_title: str,
    file_record: File,
    body: str,
    quote: str,
    requirement_code: str | None = None,
    confidence: float = 0.95,
    evidence_type: str = "policy_statement",
) -> None:
    """Run one scripted proposal through the real routing rules."""
    index = await _control_index(db, organization_id, control_title)
    await suggest_evidence_mappings(
        db,
        organization_id=organization_id,
        file_record=file_record,
        file_bytes=body.encode(),
        actor_user_id=None,
        gateway=_StubGateway(
            [
                ProposedMapping(
                    control_index=index,
                    section_index=1,
                    confidence=confidence,
                    rationale="The named section supports this control.",
                    evidence_type=evidence_type,
                    requirement_code=requirement_code,
                    quoted_passage=quote,
                )
            ]
        ),
    )
    await db.commit()


def _assert_screens_agree(listed: dict, detail: dict) -> None:
    """The assertion the whole module exists for."""
    assert listed["assessment_status"] == detail["assessment_status"], (
        listed["title"],
        listed["assessment_status"],
        detail["assessment_status"],
    )
    assert listed["assessment_status"] == detail["assessment"]["status"]
    assert listed["coverage_percent"] == detail["coverage_percent"]
    assert listed["coverage_percent"] == detail["assessment"]["confidence"]
    assert listed["assessment_label"] == detail["assessment"]["label"]


# --- Case A: no evidence ----------------------------------------------


async def test_case_a_no_evidence(client: AsyncClient) -> None:
    await _signup(client)
    await _declare(client)
    await _register_system(client, "Support Copilot", "limited")
    await _adopt(client, "eu_ai_act")

    listed = await _control_by_title(client, "Ensure staff competence in AI use")
    detail = await _detail(client, listed["id"])

    assert listed["assessment_status"] == "no_evidence"
    assert listed["assessment_label"] == "No evidence"
    assert listed["coverage_percent"] == 0
    _assert_screens_agree(listed, detail)


# --- Case B / C: partial then full coverage ---------------------------


async def test_case_b_and_c_coverage_counts_requirements_not_documents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """One document answering one of three applicable requirements is 33%.
    The same one document must not read 33% once it answers all three —
    which is what dividing documents by requirements produced."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    await _declare(client, builds_ai_features=True)
    await _register_system(client, "Credit Scoring Engine", "high")
    await _adopt(client, "eu_ai_act")
    await _adopt(client, "iso42001")

    title = "Monitor AI systems in production"
    before = await _control_by_title(client, title)
    detail_before = await _detail(client, before["id"])
    applicable = detail_before["assessment"]["applicable_count"]
    assert applicable >= 2, detail_before["assessment"]["requirements"]

    codes = [
        line["reference_code"]
        for line in detail_before["assessment"]["requirements"]
        if line["applicability"] != "not_applicable"
    ]

    # Case B: one document, attributed to one of the applicable
    # requirements. The others are untouched by it.
    document = await _upload(client, db_session, "ai-monitoring-policy.txt", MONITORING_POLICY)
    await _map_evidence(
        db_session,
        organization_id=organization_id,
        control_title=title,
        file_record=document,
        body=MONITORING_POLICY,
        quote="Product teams monitor material failures, user feedback and incidents",
        requirement_code=codes[0],
    )

    listed = await _control_by_title(client, title)
    detail = await _detail(client, listed["id"])
    _assert_screens_agree(listed, detail)

    assert listed["assessment_status"] == "partially_evidenced", detail["assessment"]["why"]
    assert listed["coverage_percent"] == round(100 / len(codes))
    assert 0 < listed["coverage_percent"] < 100

    # Case C: attribute a document to every remaining applicable
    # requirement and the figure reaches 100.
    for position, code in enumerate(codes[1:], start=2):
        extra = await _upload(
            client, db_session, f"ai-monitoring-{position}.txt", MONITORING_POLICY
        )
        await _map_evidence(
            db_session,
            organization_id=organization_id,
            control_title=title,
            file_record=extra,
            body=MONITORING_POLICY,
            quote="Accuracy, robustness and cybersecurity of each system are measured",
            requirement_code=code,
        )

    listed = await _control_by_title(client, title)
    detail = await _detail(client, listed["id"])
    _assert_screens_agree(listed, detail)
    assert listed["coverage_percent"] == 100, detail["assessment"]["why"]
    assert listed["assessment_status"] in {"evidenced", "needs_review"}


# --- Case D: a non-applicable requirement leaves the denominator ------


async def test_case_d_non_applicable_requirement_is_out_of_the_denominator(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The headline number in the report. `Monitor AI systems in
    production` serves Art. 15, Art. 72 and ISO 9.1. At a company that
    deploys no high-risk AI, Art. 72 does not bind them — so the control
    serves two applicable requirements, and one covered of two is 50%,
    not one of three at 33%."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    # A provider with a high-risk system still in development: Art. 15 is
    # a design-time obligation and binds them, Art. 72 is post-market and
    # does not begin until the system is placed on the market.
    await _declare(client, builds_ai_features=True)
    await _register_system(client, "Credit Scoring Engine", "high")
    await _adopt(client, "eu_ai_act")
    await _adopt(client, "iso42001")

    title = "Monitor AI systems in production"
    listed = await _control_by_title(client, title)
    detail = await _detail(client, listed["id"])
    lines = {line["reference_code"]: line for line in detail["assessment"]["requirements"]}

    assert "Art. 72" in lines, sorted(lines)
    assert lines["Art. 72"]["applicability"] == "not_applicable", lines["Art. 72"]
    assert lines["Art. 72"]["applicability_reason"], "an exclusion needs a reason"
    # ...while the design-time obligation on the same control does bind
    # them. The two must not move together.
    assert lines["Art. 15"]["applicability"] == "applicable", lines["Art. 15"]

    mapped = len(lines)
    in_scope = detail["assessment"]["applicable_count"]
    assert in_scope < mapped, "the excluded requirement is still in the denominator"

    # The user's premise: evidence supports 9.1 only.
    document = await _upload(client, db_session, "ai-monitoring-policy.txt", MONITORING_POLICY)
    await _map_evidence(
        db_session,
        organization_id=organization_id,
        control_title=title,
        file_record=document,
        body=MONITORING_POLICY,
        quote="Product teams monitor material failures, user feedback and incidents",
        requirement_code="9.1",
    )

    listed = await _control_by_title(client, title)
    detail = await _detail(client, listed["id"])
    _assert_screens_agree(listed, detail)

    covered = detail["assessment"]["satisfied_count"]
    in_scope = detail["assessment"]["applicable_count"]
    assert covered == 1, detail["assessment"]["requirements"]
    assert in_scope == 2, detail["assessment"]["requirements"]
    # The number in the report: 1 of 2 applicable, not 1 of 3 mapped.
    assert listed["coverage_percent"] == 50, detail["assessment"]["why"]
    assert listed["coverage_percent"] != round(100 * covered / mapped)

    # And nothing non-applicable produced a finding.
    gaps = (await client.get("/api/v1/compliance/gaps")).json()
    requirement_ids = {lines["Art. 72"]["requirement_id"]}
    assert not [g for g in gaps if g["requirement_id"] in requirement_ids]


# --- Case E: every mapped requirement is out of scope -----------------


async def test_case_e_all_requirements_out_of_scope_is_not_applicable(
    client: AsyncClient,
) -> None:
    await _signup(client)
    await _declare(client, builds_ai_features=False, uses_third_party_ai=False)
    await _adopt(client, "eu_ai_act")

    controls = (await client.get("/api/v1/compliance/controls?limit=200")).json()
    not_applicable = [c for c in controls if c["assessment_status"] == "not_applicable"]
    assert not_applicable, "no control fell out of scope for an organization running no AI"

    for listed in not_applicable:
        detail = await _detail(client, listed["id"])
        _assert_screens_agree(listed, detail)
        assert listed["applicable_requirement_count"] == 0
        assert listed["coverage_percent"] == 0
        lines = detail["assessment"]["requirements"]
        assert lines, listed["title"]
        assert all(line["applicability"] == "not_applicable" for line in lines)

        # No finding, and nothing to remediate.
        gaps = (await client.get("/api/v1/compliance/gaps")).json()
        ids = {line["requirement_id"] for line in lines}
        assert not [g for g in gaps if g["requirement_id"] in ids], listed["title"]


# --- Case F: ambiguous evidence ---------------------------------------


async def test_case_f_ambiguous_evidence_needs_review_without_a_gap(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Evidence that cannot be confirmed is a question, not a finding."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    await _declare(client, builds_ai_features=True)
    await _register_system(client, "Credit Scoring Engine", "high")
    await _adopt(client, "eu_ai_act")

    title = "Monitor AI systems in production"
    document = await _upload(client, db_session, "ai-monitoring-policy.txt", MONITORING_POLICY)
    await _map_evidence(
        db_session,
        organization_id=organization_id,
        control_title=title,
        file_record=document,
        body=MONITORING_POLICY,
        quote="Product teams monitor material failures, user feedback and incidents",
    )

    listed = await _control_by_title(client, title)
    detail = await _detail(client, listed["id"])
    _assert_screens_agree(listed, detail)

    # Art. 15 and Art. 72 have no itemised expectation set, so a covering
    # conclusion cannot be drawn from a single policy statement.
    lines = detail["assessment"]["requirements"]
    uncertain = [line for line in lines if line["coverage"] == "uncertain"]
    assert uncertain, [line["coverage"] for line in lines]

    # Whatever the control-level roll-up, none of those requirements may
    # have produced a confirmed finding.
    gaps = (await client.get("/api/v1/compliance/gaps")).json()
    by_requirement = {g["requirement_id"]: g for g in gaps}
    for line in uncertain:
        assert line["requirement_id"] not in by_requirement, line["reference_code"]


# --- The acceptance walk ----------------------------------------------


async def test_every_control_agrees_between_the_list_and_its_own_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Globally, not for the one control that was reported.

    This is the assertion that would have caught the original bug: it
    fails for every control whose stored workflow status disagrees with
    the derived one, which was all of them.
    """
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    await _declare(client, builds_ai_features=True)
    await _register_system(client, "Credit Scoring Engine", "high")
    await _register_system(client, "Support Copilot", "limited")
    await _adopt(client, "eu_ai_act")
    await _adopt(client, "iso42001")
    await _adopt(client, "gdpr")

    document = await _upload(client, db_session, "ai-monitoring-policy.txt", MONITORING_POLICY)
    await _map_evidence(
        db_session,
        organization_id=organization_id,
        control_title="Monitor AI systems in production",
        file_record=document,
        body=MONITORING_POLICY,
        quote="Product teams monitor material failures, user feedback and incidents",
    )

    controls = (await client.get("/api/v1/compliance/controls?limit=200")).json()
    assert len(controls) > 5, "not enough controls to call this a global check"

    for listed in controls:
        detail = await _detail(client, listed["id"])
        _assert_screens_agree(listed, detail)

        # The percentage is always over the applicable count.
        assessment = detail["assessment"]
        if assessment["applicable_count"]:
            assert listed["coverage_percent"] == round(
                100 * assessment["satisfied_count"] / assessment["applicable_count"]
            ), listed["title"]
        else:
            assert listed["assessment_status"] == "not_applicable"
            assert listed["coverage_percent"] == 0

        # The stored workflow field is never presented as the assessment.
        assert listed["assessment_status"] not in {"not_started", "implemented"}


async def test_a_high_risk_obligation_binds_one_system_and_not_another(
    client: AsyncClient,
) -> None:
    """Organization -> AI system -> role -> risk class -> applicable.

    Adopting the EU AI Act must not apply a high-risk obligation to every
    registered system indiscriminately, and the per-system answers have to
    survive rather than being flattened to one organization-level yes.
    """
    await _signup(client)
    await _declare(client, builds_ai_features=True)
    # Live and high risk, so post-market monitoring has actually begun.
    high = await _register_system(
        client, "Credit Scoring Engine", "high", deployment="production"
    )
    low = await _register_system(client, "Support Copilot", "limited")
    framework_id = await _adopt(client, "eu_ai_act")

    result = (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()
    art72 = next(r for r in result["requirements"] if r["reference_code"] == "Art. 72")
    assert art72["status"] != "not_applicable", art72["summary"]

    # It binds the high-risk engine, and says so by name — not the
    # support assistant.
    control = await _control_by_title(client, "Monitor AI systems in production")
    detail = await _detail(client, control["id"])
    line = next(
        line
        for line in detail["assessment"]["requirements"]
        if line["reference_code"] == "Art. 72"
    )
    assert line["applicability"] == "applicable"
    assert "Credit Scoring Engine" in line["applicability_reason"]
    assert "Support Copilot" not in line["applicability_reason"]
    assert high != low


# --- Grammar -----------------------------------------------------------


async def test_customer_facing_strings_are_written_in_english(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`1 piece(s) of evidence are mapped` is the sort of thing that makes
    a product feel machine-generated exactly where it is asking to be
    trusted."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    await _declare(client, builds_ai_features=True)
    await _register_system(client, "Credit Scoring Engine", "high")
    await _adopt(client, "eu_ai_act")

    document = await _upload(client, db_session, "ai-monitoring-policy.txt", MONITORING_POLICY)
    await _map_evidence(
        db_session,
        organization_id=organization_id,
        control_title="Monitor AI systems in production",
        file_record=document,
        body=MONITORING_POLICY,
        quote="Product teams monitor material failures, user feedback and incidents",
    )

    controls = (await client.get("/api/v1/compliance/controls?limit=200")).json()
    for listed in controls:
        detail = await _detail(client, listed["id"])
        why = detail["assessment"]["why"]
        for tell in ("(s)", "piece(s)", "requirement(s)", "  "):
            assert tell not in why, (listed["title"], why)
        assert "1 pieces" not in why
        assert "1 piece of evidence is mapped" in why or "1 piece" not in why
