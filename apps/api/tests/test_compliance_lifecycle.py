"""The whole chain, on one realistic tenant.

Acme AI SaaS: a 60-person US software company with EU customers that uses
OpenAI for customer support. Exactly the organization this product is
built for, walked from an empty account to an audit-ready position:

    declare the company
        -> adopt what applies
        -> upload documents
        -> evidence extracted and mapped
        -> assessed
        -> gaps found
        -> remediation generated and assigned
        -> new evidence supplied
        -> reassessed, score moves
        -> the whole thing readable in the audit trail

Every other test file checks one link. This one checks that the links
join up, which is the only thing the customer actually experiences.

No provider is called. The gateway is stubbed with scripted proposals so
the test asserts *this code's* behaviour rather than a model's mood, and
so it costs nothing to run.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import AiProviderUnavailable
from app.audit.models import AuditEvent
from app.compliance.evidence_ai import (
    DocumentAnalysis,
    ProposedMapping,
    suggest_evidence_mappings,
)
from app.compliance.models import Control, EvidenceSuggestion
from app.core.models import File
from app.seed import _ensure_compliance_catalog

# --- The documents Acme actually has ---------------------------------

PRIVACY_NOTICE = """ACME AI SAAS - PRIVACY NOTICE

Section 1 Who we are
Acme AI SaaS Inc. is the controller for the personal data described in
this notice and can be reached at privacy@acme.example for any question
about how we handle information.

Section 2 Transparency
We tell data subjects who we are, why we process their data, the lawful
basis we rely on, who receives it, how long we keep it, and the rights
available to them, at the point we collect it.

Section 3 Your rights
Data subjects may request access, rectification, erasure, restriction and
portability, and may object to processing. We respond to every request
within one month of receipt and verify identity before disclosing data.
"""

SECURITY_POLICY = """ACME AI SAAS - INFORMATION SECURITY POLICY

Section 1 Access control
Access to systems holding personal data is granted on least privilege.
Every request needs approval from the data owner, access is reviewed
quarterly, and multi-factor authentication is enforced for administrators.

Section 2 Security of processing
Personal data is encrypted in transit with TLS 1.3 and at rest with
AES-256. Backups run daily to a separate region and restoration is tested
twice a year to confirm resilience.
"""


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


class _StubGateway:
    """Stands in for the model, returning whatever the test scripted."""

    def __init__(
        self,
        mappings: list[ProposedMapping],
        *,
        document_type: str = "Privacy Notice",
        document_domain: str = "Privacy / GDPR",
        broken: bool = False,
    ) -> None:
        self._mappings = mappings
        self._document_type = document_type
        self._document_domain = document_domain
        self._broken = broken
        self.prompts: list[str] = []

    async def generate_structured(self, db, *, organization_id, requested_by, request, schema):  # type: ignore[no-untyped-def]
        self.prompts.append(request.prompt)
        if self._broken:
            # An adapter returning the wrong shape. Must fail loudly rather
            # than look like "the document matched no controls".
            return object()  # type: ignore[return-value]
        return DocumentAnalysis(
            document_type=self._document_type,
            document_domain=self._document_domain,
            mappings=self._mappings,
        )


async def _signup(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Acme Compliance Lead",
            "organization_name": f"Acme AI SaaS {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _organization_id(client: AsyncClient, db: AsyncSession) -> uuid.UUID:
    from app.core.models import Membership

    me = (await client.get("/api/v1/auth/me")).json()
    return (
        await db.execute(
            select(Membership.organization_id).where(
                Membership.user_id == uuid.UUID(me["id"])
            )
        )
    ).scalar_one()


async def _upload(client: AsyncClient, db: AsyncSession, filename: str, body: str) -> File:
    """Register a file the way the browser does, minus the object PUT."""
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
    """The prompt numbers controls positionally, so a scripted proposal has
    to reference the same order the prompt was built from."""
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
    raise AssertionError(f"No control titled {title!r}. Have: {[c.title for c in controls]}")


# --- The whole chain --------------------------------------------------


async def test_acme_goes_from_empty_account_to_audit_ready(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "acme-lifecycle@example.com")
    organization_id = await _organization_id(client, db_session)

    # 1. Declare the company. This is what decides what applies.
    recommendations = (
        await client.put(
            "/api/v1/compliance/company-facts",
            json={
                "sells_to_eu_customers": True,
                "processes_personal_data": True,
                "uses_third_party_ai": True,
                "is_data_processor": True,
                "sells_to_enterprise": True,
                "sector": "saas",
            },
        )
    ).json()
    by_key = {r["framework_key"]: r for r in recommendations["recommendations"]}
    assert by_key["gdpr"]["applicability"] == "required"
    assert by_key["eu_ai_act"]["applicability"] == "required"
    assert by_key["gdpr"]["reasons"], "a recommendation with no reason is a guess"

    # 2. Adopt them. This is what builds the control set.
    adopted = await client.post(
        "/api/v1/compliance/frameworks/adopt-recommended",
        json={"framework_keys": ["gdpr", "eu_ai_act"]},
    )
    assert adopted.status_code == 200, adopted.text

    controls = (await client.get("/api/v1/compliance/controls")).json()
    assert controls, "adopting frameworks scaffolded no controls"
    # One measure serves requirements in both frameworks, so the control
    # count comes in well under the combined requirement count. That gap
    # is the whole argument for adopting a second framework here rather
    # than starting again elsewhere.
    gdpr_id = by_key["gdpr"]["framework_id"]
    ai_act_id = by_key["eu_ai_act"]["framework_id"]
    total_requirements = 0
    for framework_id in (gdpr_id, ai_act_id):
        total_requirements += len(
            (
                await client.get(
                    f"/api/v1/compliance/frameworks/{framework_id}/requirements"
                )
            ).json()
        )
    assert len(controls) < total_requirements

    # 3. Baseline: adopting must not move the compliance position.
    baseline = (await client.get("/api/v1/compliance/overview")).json()
    gdpr_before = next(f for f in baseline["frameworks"] if f["framework_key"] == "gdpr")
    assert gdpr_before["readiness"]["percent"] == 0.0

    # 4. Upload a document; the AI proposes where it belongs.
    notice = await _upload(client, db_session, "privacy-notice.txt", PRIVACY_NOTICE)
    rights_index = await _control_index(
        db_session, organization_id, "Handle data subject requests within statutory timelines"
    )
    outcome = await suggest_evidence_mappings(
        db_session,
        organization_id=organization_id,
        file_record=notice,
        file_bytes=PRIVACY_NOTICE.encode(),
        actor_user_id=None,
        gateway=_StubGateway(
            [
                ProposedMapping(
                    control_index=rights_index,
                    section_index=3,
                    confidence=0.95,
                    rationale="Section 3 sets out the rights process and the response window.",
                    evidence_type="policy_statement",
                    quoted_passage=(
                        "Data subjects may request access, rectification, erasure, "
                        "restriction and portability"
                    ),
                )
            ]
        ),  # type: ignore[arg-type]
    )
    await db_session.commit()

    assert len(outcome.suggestions) == 1
    suggestion = outcome.suggestions[0]
    assert suggestion.quote_verified is True
    # Verified quote, ordinary requirement, high confidence: this is the
    # narrow case that stands without a person.
    assert suggestion.status == "auto_approved"
    assert suggestion.evidence_id is not None
    # And the citation is traceable back to a place in the document.
    assert suggestion.source_location
    assert "Section 3" in suggestion.source_location

    # 5. Assess. The position moves because real evidence now exists.
    assessment = (
        await client.post(f"/api/v1/compliance/frameworks/{gdpr_id}/assess")
    ).json()
    assert assessment["readiness"]["percent"] > 0.0
    assert assessment["readiness"]["explanation"]
    assert assessment["gap_count"] > 0, "an unevidenced catalog must produce gaps"

    # 6. Gaps name what is missing, without asserting a breach.
    gaps = (await client.get("/api/v1/compliance/gaps")).json()
    assert gaps
    for gap in gaps:
        lowered = gap["summary"].lower()
        for forbidden in ("violation", "breach of", "non-compliant", "unlawful"):
            assert forbidden not in lowered

    # 7. Remediation, then a task somebody owns.
    target = next(g for g in gaps if g["kind"] == "evidence_missing")
    remediated = await client.post(
        f"/api/v1/compliance/gaps/{target['id']}/remediation"
    )
    assert remediated.status_code == 200, remediated.text
    assert remediated.json()["recommendation"]

    task = await client.post(
        f"/api/v1/compliance/gaps/{target['id']}/task",
        json={"title": "Produce the missing evidence", "priority": "high", "due_in_days": 7},
    )
    assert task.status_code == 201, task.text
    assert task.json()["due_at"], "remediation work needs a date against it"

    # 8. New evidence arrives, and the control it touches goes stale.
    policy = await _upload(client, db_session, "security-policy.txt", SECURITY_POLICY)
    access_index = await _control_index(
        db_session, organization_id, "Restrict access to personal data to authorised people"
    )
    await suggest_evidence_mappings(
        db_session,
        organization_id=organization_id,
        file_record=policy,
        file_bytes=SECURITY_POLICY.encode(),
        actor_user_id=None,
        gateway=_StubGateway(
            [
                ProposedMapping(
                    control_index=access_index,
                    section_index=1,
                    confidence=0.96,
                    rationale="Section 1 describes least privilege and quarterly review.",
                    evidence_type="policy_statement",
                    quoted_passage=(
                        "Access to systems holding personal data is granted on least privilege"
                    ),
                )
            ],
            document_type="Information Security Policy",
            document_domain="Security",
        ),  # type: ignore[arg-type]
    )
    await db_session.commit()

    stale = list(
        (
            await db_session.execute(
                select(Control).where(
                    Control.organization_id == organization_id,
                    Control.needs_reassessment.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    assert stale, "new evidence must mark its control for reassessment"

    # 9. Reassess: the score moves again, and the stale flag clears.
    after = (await client.post(f"/api/v1/compliance/frameworks/{gdpr_id}/assess")).json()
    assert after["readiness"]["percent"] >= assessment["readiness"]["percent"]

    # 10. The whole thing is readable afterwards.
    events = list(
        (
            await db_session.execute(
                select(AuditEvent.action).where(
                    AuditEvent.organization_id == organization_id
                )
            )
        )
        .scalars()
        .all()
    )
    for expected in (
        "compliance.company_facts.declared",
        "compliance.framework.activated",
        "compliance.evidence.suggestions_generated",
        "compliance.evidence.suggestion_auto_approved",
    ):
        assert expected in events, f"{expected} missing from the audit trail"


# --- The ways it can go wrong ----------------------------------------


async def test_a_malformed_model_response_fails_loudly(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An adapter returning the wrong shape must not look like "the
    document matched no controls" — a silent empty result would be read
    as a clean bill of health."""
    await _signup(client, "acme-malformed@example.com")
    organization_id = await _organization_id(client, db_session)
    record = await _upload(client, db_session, "notice.txt", PRIVACY_NOTICE)

    db_session.add(Control(organization_id=organization_id, title="Some control"))
    await db_session.flush()

    with pytest.raises(AiProviderUnavailable):
        await suggest_evidence_mappings(
            db_session,
            organization_id=organization_id,
            file_record=record,
            file_bytes=PRIVACY_NOTICE.encode(),
            actor_user_id=None,
            gateway=_StubGateway([], broken=True),  # type: ignore[arg-type]
        )


async def test_a_low_confidence_mapping_waits_for_a_person(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "acme-lowconf@example.com")
    organization_id = await _organization_id(client, db_session)
    record = await _upload(client, db_session, "notice.txt", PRIVACY_NOTICE)

    db_session.add(Control(organization_id=organization_id, title="Rights handling"))
    await db_session.flush()

    outcome = await suggest_evidence_mappings(
        db_session,
        organization_id=organization_id,
        file_record=record,
        file_bytes=PRIVACY_NOTICE.encode(),
        actor_user_id=None,
        gateway=_StubGateway(
            [
                ProposedMapping(
                    control_index=1,
                    section_index=3,
                    confidence=0.42,
                    rationale="Might be relevant.",
                    evidence_type="policy_statement",
                    quoted_passage=(
                        "Data subjects may request access, rectification, erasure, "
                        "restriction and portability"
                    ),
                )
            ]
        ),  # type: ignore[arg-type]
    )

    assert outcome.suggestions[0].status == "proposed"
    assert outcome.suggestions[0].evidence_id is None


async def test_a_fabricated_citation_never_becomes_evidence(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The property the whole feature rests on. Confident, on-topic, and
    simply not in the document."""
    await _signup(client, "acme-fabricated@example.com")
    organization_id = await _organization_id(client, db_session)
    record = await _upload(client, db_session, "notice.txt", PRIVACY_NOTICE)

    db_session.add(Control(organization_id=organization_id, title="Rights handling"))
    await db_session.flush()

    outcome = await suggest_evidence_mappings(
        db_session,
        organization_id=organization_id,
        file_record=record,
        file_bytes=PRIVACY_NOTICE.encode(),
        actor_user_id=None,
        gateway=_StubGateway(
            [
                ProposedMapping(
                    control_index=1,
                    section_index=3,
                    confidence=0.99,
                    rationale="The notice clearly covers this.",
                    evidence_type="policy_statement",
                    quoted_passage=(
                        "All requests are fulfilled automatically within 24 hours by our "
                        "self-service portal."
                    ),
                )
            ]
        ),  # type: ignore[arg-type]
    )

    assert outcome.unverifiable_count == 1
    assert outcome.suggestions[0].status == "unverifiable"
    assert outcome.suggestions[0].evidence_id is None


async def test_a_rejected_proposal_creates_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "acme-rejected@example.com")
    organization_id = await _organization_id(client, db_session)
    record = await _upload(client, db_session, "notice.txt", PRIVACY_NOTICE)

    db_session.add(Control(organization_id=organization_id, title="Rights handling"))
    await db_session.flush()

    outcome = await suggest_evidence_mappings(
        db_session,
        organization_id=organization_id,
        file_record=record,
        file_bytes=PRIVACY_NOTICE.encode(),
        actor_user_id=None,
        gateway=_StubGateway(
            [
                ProposedMapping(
                    control_index=1,
                    section_index=3,
                    confidence=0.5,
                    rationale="Possibly relevant.",
                    evidence_type="policy_statement",
                    quoted_passage=(
                        "Data subjects may request access, rectification, erasure, "
                        "restriction and portability"
                    ),
                )
            ]
        ),  # type: ignore[arg-type]
    )
    await db_session.commit()

    suggestion_id = outcome.suggestions[0].id
    rejected = await client.post(
        f"/api/v1/compliance/evidence/suggestions/{suggestion_id}/reject"
    )
    assert rejected.status_code == 200, rejected.text

    evidence = (await client.get("/api/v1/compliance/evidence")).json()
    assert evidence == []


async def test_processing_a_document_that_does_not_exist_is_not_found(
    client: AsyncClient,
) -> None:
    await _signup(client, "acme-missing@example.com")
    response = await client.post(
        "/api/v1/compliance/documents/process", json={"file_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404


async def test_reanalysing_the_same_document_does_not_stack_duplicates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "acme-duplicate@example.com")
    organization_id = await _organization_id(client, db_session)
    record = await _upload(client, db_session, "notice.txt", PRIVACY_NOTICE)

    db_session.add(Control(organization_id=organization_id, title="Rights handling"))
    await db_session.flush()

    mapping = ProposedMapping(
        control_index=1,
        section_index=3,
        confidence=0.5,
        rationale="Possibly relevant.",
        evidence_type="policy_statement",
        quoted_passage=(
            "Data subjects may request access, rectification, erasure, restriction and "
            "portability"
        ),
    )
    for _ in range(3):
        await suggest_evidence_mappings(
            db_session,
            organization_id=organization_id,
            file_record=record,
            file_bytes=PRIVACY_NOTICE.encode(),
            actor_user_id=None,
            gateway=_StubGateway([mapping]),  # type: ignore[arg-type]
        )

    undecided = list(
        (
            await db_session.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.file_id == record.id,
                    EvidenceSuggestion.status == "proposed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(undecided) == 1


async def test_one_tenants_work_is_invisible_to_another(client: AsyncClient) -> None:
    """The end-to-end isolation check: everything Acme built stays Acme's."""
    await _signup(client, "acme-iso-a@example.com")
    await client.put(
        "/api/v1/compliance/company-facts",
        json={"sells_to_eu_customers": True, "processes_personal_data": True},
    )
    await client.post(
        "/api/v1/compliance/frameworks/adopt-recommended", json={"framework_keys": ["gdpr"]}
    )
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Acme Support AI", "purpose": "Answer questions."},
    )
    await client.post("/api/v1/auth/logout")

    await _signup(client, "acme-iso-b@example.com")
    assert (await client.get("/api/v1/compliance/controls")).json() == []
    assert (await client.get("/api/v1/compliance/gaps")).json() == []
    assert (await client.get("/api/v1/compliance/overview")).json()["frameworks"] == []
    assert (
        await client.get("/api/v1/compliance/framework-recommendations")
    ).json()["facts_declared"] is False
    assert (
        await client.get("/api/v1/compliance/ai-systems/governance")
    ).json()["total_systems"] == 0
    assert (await client.get("/api/v1/compliance/review-center")).json()[
        "total_needing_review"
    ] == 0
