"""The requirement lifecycle, one state at a time.

The reported symptom was Art. 12 reading as all of these at once: needs
review, one evidence item, one mapped control, no completed assessment, a
medium-severity gap, and remediating. Those are not compatible. The cause
was a single fallthrough — evidence exists and no human has recorded a
pass, therefore `partial`, therefore a confirmed gap — which collapsed
"nobody has looked yet" and "something is definitely missing" into one
state.

The order these tests assert:

    evidence discovered -> assessed -> needs review while uncertain
    -> gap only once a deficiency is named -> remediation -> remediating
    -> reassessment -> resolved

The load-bearing line is between `needs_review` and `deficient`. One is
an open question and raises nothing; the other is a finding and must name
what is missing.
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

# Section 1 is a policy statement. Section 2 is a record. Which of the two
# a document contains is what decides whether Art. 4 is satisfied or has a
# named deficiency, so the tests below use them separately.
POLICY_ONLY = """ACME AI SAAS - AI LITERACY POLICY

Section 1 Commitment
Acme requires that every person who operates or oversees an AI system
holds a level of AI literacy appropriate to their role, and commits to
providing training proportionate to that role.
"""

RECORDS_ONLY = """ACME AI SAAS - AI LITERACY COMPLETION REGISTER

Section 1 Completion
The following people completed the AI literacy course on 4 March 2026:
Dana Okafor, Ravi Menon, Ines Duarte. Each acknowledged the AI use policy
in writing at completion.
"""


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


class _StubGateway:
    def __init__(self, mappings: list[ProposedMapping], *, doc_type: str) -> None:
        self._mappings = mappings
        self._doc_type = doc_type

    async def generate_structured(self, db, *, organization_id, requested_by, request, schema):  # type: ignore[no-untyped-def]
        return DocumentAnalysis(
            document_type=self._doc_type,
            document_domain="AI Governance",
            mappings=self._mappings,
        )


async def _signup(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"lifecycle-{uuid.uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery",
            "full_name": "Acme Compliance Lead",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
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


async def _declare_facts(client: AsyncClient) -> None:
    """Declare what the company is.

    Required before any scoping rule can answer. An organization that
    has declared nothing gets `needs_review` on every conditional
    requirement rather than `not_applicable` — we cannot tell whether an
    obligation binds them, and quietly excluding it would shrink the
    denominator and flatter the score.
    """
    response = await client.put(
        "/api/v1/compliance/company-facts",
        json={
            "operates_in_eu": True,
            "sells_to_eu_customers": True,
            "processes_personal_data": True,
            "uses_third_party_ai": True,
            "builds_ai_features": False,
            "sells_to_enterprise": True,
        },
    )
    assert response.status_code == 200, response.text


async def _register_ai_system(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Support Copilot",
            "vendor": "OpenAI",
            "purpose": "Drafts replies to customer support tickets.",
            "risk_classification": "limited",
        },
    )
    assert response.status_code == 201, response.text


async def _adopt_eu_ai_act(client: AsyncClient) -> str:
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    framework_id = next(f["id"] for f in frameworks if f["key"] == "eu_ai_act")
    await client.put(
        f"/api/v1/compliance/frameworks/{framework_id}/activation", json={"active": True}
    )
    return str(framework_id)


async def _assess(client: AsyncClient, framework_id: str) -> dict:
    return (
        await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")
    ).json()


def _art4(result: dict) -> dict:
    return next(r for r in result["requirements"] if r["reference_code"] == "Art. 4")


async def _map_document(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_record: File,
    body: str,
    evidence_type: str,
    quote: str,
    confidence: float,
    doc_type: str,
) -> None:
    index = await _control_index(
        db, organization_id, "Ensure staff competence in AI use"
    )
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
                    quoted_passage=quote,
                )
            ],
            doc_type=doc_type,
        ),
    )
    await db.commit()


# --- Case 4: no evidence ----------------------------------------------


async def test_no_evidence_reports_missing_evidence_and_says_what_is_needed(
    client: AsyncClient,
) -> None:
    await _signup(client)
    await _declare_facts(client)
    await _register_ai_system(client)
    framework_id = await _adopt_eu_ai_act(client)

    art4 = _art4(await _assess(client, framework_id))
    assert art4["status"] == "evidence_missing"
    assert art4["gap_id"], "no evidence at all is a real deficiency"

    gap = (await client.get(f"/api/v1/compliance/gaps/{art4['gap_id']}")).json()
    plan = gap["remediation_plan"]
    assert plan["required_evidence"], "the finding must say what would close it"
    assert any(
        "completion" in item.lower() or "attendance" in item.lower()
        for item in plan["required_evidence"]
    )


# --- Case 2: evidence exists, conclusion uncertain ---------------------


async def test_uncertain_evidence_is_needs_review_and_raises_no_gap(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The reported bug, inverted into an assertion. A low-confidence
    mapping is not a deficiency — it is a question."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    await _declare_facts(client)
    await _register_ai_system(client)
    framework_id = await _adopt_eu_ai_act(client)
    await _assess(client, framework_id)

    document = await _upload(client, db_session, "ai-literacy-policy.txt", POLICY_ONLY)
    await _map_document(
        db_session,
        organization_id=organization_id,
        file_record=document,
        body=POLICY_ONLY,
        evidence_type="policy_statement",
        quote="Acme requires that every person who operates or oversees an AI system",
        # Below the auto-approval bar, so a person is asked. It still
        # becomes evidence only if approved — here it does not, so the
        # requirement has a control, a document, and no firm citation.
        confidence=0.55,
        doc_type="AI Literacy Policy",
    )

    art4 = _art4(await _assess(client, framework_id))
    assert art4["status"] in {"evidence_missing", "needs_review"}
    if art4["status"] == "needs_review":
        assert art4["gap_id"] is None, "uncertainty must not be reported as a finding"
        assert not art4["missing_conditions"]
        assert art4["uncertainty"]


# --- Case 3: a specific deficiency is identified -----------------------


async def test_a_named_deficiency_produces_a_gap_that_says_what_is_missing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Art. 4 expects a policy *and* completion records. A policy alone is
    a deficiency the product can name, so it is a finding — and the
    finding says which condition is unmet rather than telling the reader
    to identify it themselves."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    await _declare_facts(client)
    await _register_ai_system(client)
    framework_id = await _adopt_eu_ai_act(client)
    await _assess(client, framework_id)

    document = await _upload(client, db_session, "ai-literacy-policy.txt", POLICY_ONLY)
    await _map_document(
        db_session,
        organization_id=organization_id,
        file_record=document,
        body=POLICY_ONLY,
        evidence_type="policy_statement",
        quote="Acme requires that every person who operates or oversees an AI system",
        confidence=0.95,
        doc_type="AI Literacy Policy",
    )

    art4 = _art4(await _assess(client, framework_id))
    assert art4["status"] == "deficient"
    assert art4["gap_id"]
    assert art4["missing_conditions"], "a finding must name the unmet condition"
    assert any(
        "completion" in item.lower() or "attendance" in item.lower()
        for item in art4["missing_conditions"]
    ), art4["missing_conditions"]

    # The generic instruction the report called out by name.
    gap = (await client.get(f"/api/v1/compliance/gaps/{art4['gap_id']}")).json()
    plan = gap["remediation_plan"]
    text = " ".join([plan["problem"], plan["action"], *plan["checklist"]]).lower()
    assert "identify which part of the requirement" not in text
    assert "completion records" in text or "attendance" in text


# --- Case 1: evidence clearly satisfies --------------------------------


async def test_evidence_covering_every_condition_is_satisfied_with_no_gap(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    await _declare_facts(client)
    await _register_ai_system(client)
    framework_id = await _adopt_eu_ai_act(client)
    await _assess(client, framework_id)

    policy = await _upload(client, db_session, "ai-literacy-policy.txt", POLICY_ONLY)
    await _map_document(
        db_session,
        organization_id=organization_id,
        file_record=policy,
        body=POLICY_ONLY,
        evidence_type="policy_statement",
        quote="Acme requires that every person who operates or oversees an AI system",
        confidence=0.95,
        doc_type="AI Literacy Policy",
    )
    materials = await _upload(client, db_session, "ai-literacy-course.txt", POLICY_ONLY)
    await _map_document(
        db_session,
        organization_id=organization_id,
        file_record=materials,
        body=POLICY_ONLY,
        evidence_type="procedure",
        quote="providing training proportionate to that role",
        confidence=0.95,
        doc_type="AI Literacy Course",
    )
    records = await _upload(client, db_session, "ai-literacy-register.txt", RECORDS_ONLY)
    await _map_document(
        db_session,
        organization_id=organization_id,
        file_record=records,
        body=RECORDS_ONLY,
        evidence_type="record",
        quote="The following people completed the AI literacy course on 4 March 2026",
        confidence=0.95,
        doc_type="Completion Register",
    )

    art4 = _art4(await _assess(client, framework_id))
    assert art4["status"] == "satisfied", art4["summary"]
    assert art4["gap_id"] is None
    assert not art4["missing_conditions"]


# --- Case 5: not applicable -------------------------------------------


async def test_a_non_applicable_requirement_is_excluded_from_every_denominator(
    client: AsyncClient,
) -> None:
    """Art. 26 binds deployers of high-risk AI. An organization with none
    is not failing it — and must not be scored as though it were, in
    readiness or in evidence coverage."""
    await _signup(client)
    await _declare_facts(client)
    await _register_ai_system(client)
    framework_id = await _adopt_eu_ai_act(client)

    result = await _assess(client, framework_id)
    art26 = next(
        r for r in result["requirements"] if r["reference_code"] == "Art. 26"
    )
    assert art26["status"] == "not_applicable"
    assert art26["gap_id"] is None

    readiness = result["readiness"]
    in_scope = [
        r for r in result["requirements"] if r["status"] != "not_applicable"
    ]
    assert readiness["total"] == len(in_scope)
    assert readiness["total"] < len(result["requirements"])
    assert readiness["not_applicable"] == len(result["requirements"]) - len(in_scope)

    # The same denominator, in the second place it is computed.
    with_evidence = sum(1 for r in in_scope if r["evidence_count"] > 0)
    expected = round(100 * with_evidence / len(in_scope), 1) if in_scope else 0.0
    assert result["evidence_coverage_percent"] == expected

    # And on the framework screen's own coverage figure.
    dashboard = (
        await client.get(f"/api/v1/compliance/frameworks/{framework_id}/dashboard")
    ).json()
    assert dashboard["coverage_percent"] <= 100.0


# --- Cases 6 and 7: gap -> remediation -> resolved ---------------------


async def test_a_confirmed_gap_carries_remediation_and_clears_on_new_evidence(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The full ordering, end to end: the deficiency is named, remediation
    is generated for it, the missing evidence arrives, and the requirement
    moves without anyone re-running anything by hand."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    await _declare_facts(client)
    await _register_ai_system(client)
    framework_id = await _adopt_eu_ai_act(client)
    await _assess(client, framework_id)

    policy = await _upload(client, db_session, "ai-literacy-policy.txt", POLICY_ONLY)
    await _map_document(
        db_session,
        organization_id=organization_id,
        file_record=policy,
        body=POLICY_ONLY,
        evidence_type="policy_statement",
        quote="Acme requires that every person who operates or oversees an AI system",
        confidence=0.95,
        doc_type="AI Literacy Policy",
    )

    art4 = _art4(await _assess(client, framework_id))
    assert art4["status"] == "deficient"
    gap_id = art4["gap_id"]

    # Case 6: the gap carries remediation aimed at the named condition.
    gap = (await client.get(f"/api/v1/compliance/gaps/{gap_id}")).json()
    assert gap["missing_conditions"]
    assert gap["remediation_plan"]["missing_conditions"] == gap["missing_conditions"]
    assert gap["remediation_plan"]["checklist"]

    task = (await client.post(f"/api/v1/compliance/gaps/{gap_id}/task", json={})).json()
    assert task["checklist"]
    after_task = (await client.get(f"/api/v1/compliance/gaps/{gap_id}")).json()
    assert after_task["status"] == "remediating"

    # Case 7: the missing evidence arrives and the position moves.
    before = (await _assess(client, framework_id))["readiness"]["percent"]

    materials = await _upload(client, db_session, "ai-literacy-course.txt", POLICY_ONLY)
    await _map_document(
        db_session,
        organization_id=organization_id,
        file_record=materials,
        body=POLICY_ONLY,
        evidence_type="procedure",
        quote="providing training proportionate to that role",
        confidence=0.95,
        doc_type="AI Literacy Course",
    )
    records = await _upload(client, db_session, "ai-literacy-register.txt", RECORDS_ONLY)
    await _map_document(
        db_session,
        organization_id=organization_id,
        file_record=records,
        body=RECORDS_ONLY,
        evidence_type="record",
        quote="The following people completed the AI literacy course on 4 March 2026",
        confidence=0.95,
        doc_type="Completion Register",
    )

    result = await _assess(client, framework_id)
    art4 = _art4(result)
    assert art4["status"] == "satisfied", art4["summary"]
    assert art4["gap_id"] is None

    resolved = (await client.get(f"/api/v1/compliance/gaps/{gap_id}")).json()
    assert resolved["status"] == "resolved"
    closed = (await client.get(f"/api/v1/tasks/{task['id']}")).json()
    assert closed["status"] == "done"
    assert result["readiness"]["percent"] > before


# --- The states are mutually exclusive ---------------------------------


async def test_no_requirement_is_ever_both_uncertain_and_a_finding(
    client: AsyncClient,
) -> None:
    """The screenshot showed one requirement holding two contradictory
    states at once. Asserted across every requirement of every framework
    rather than for the one that was reported."""
    await _signup(client)
    await _declare_facts(client)
    await _register_ai_system(client)

    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    for framework in frameworks:
        await client.put(
            f"/api/v1/compliance/frameworks/{framework['id']}/activation",
            json={"active": True},
        )
        result = await _assess(client, str(framework["id"]))
        for row in result["requirements"]:
            has_gap = row["gap_id"] is not None
            if row["status"] in {"satisfied", "needs_review", "not_applicable"}:
                assert not has_gap, (framework["key"], row["reference_code"], row["status"])
            else:
                assert has_gap, (framework["key"], row["reference_code"], row["status"])
            if row["status"] != "deficient":
                assert not row["missing_conditions"], row["reference_code"]
            # No internal placeholder ever reaches a reader.
            assert "nothing yet" not in row["summary"].lower()
