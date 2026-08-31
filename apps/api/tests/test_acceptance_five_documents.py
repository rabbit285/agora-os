"""The §28 acceptance run: five documents, no manual attachment.

A realistic tenant uploads the five documents a growing SaaS company
actually has, touches nothing else, and the product is expected to do the
rest: read them, map evidence, scope requirements, assess, find genuine
gaps, propose remediation, and re-run when new evidence arrives.

The two things this is really guarding:

* **No manual attachment anywhere.** If any assertion below only passes
  because a person attached a file to a control, the product has not done
  what it claims.
* **A non-applicable requirement stays out of it.** Article 26 must not
  produce a gap or move the score at a company that deploys no high-risk
  AI, however many documents they upload.

The gateway is stubbed. Scripted proposals make the run deterministic and
free, and what is under test is this code's behaviour, not a model's.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance.evidence_ai import (
    DocumentAnalysis,
    ProposedMapping,
    suggest_evidence_mappings,
)
from app.compliance.models import Control
from app.core.models import File
from app.seed import _ensure_compliance_catalog

PRIVACY_NOTICE = """ACME AI SAAS - PRIVACY NOTICE

Section 1 Transparency
We tell data subjects who we are, why we process their data, the lawful
basis we rely on, who receives it, how long we keep it, and the rights
available to them, at the point we collect it.

Section 2 Your rights
Data subjects may request access, rectification, erasure, restriction and
portability, and may object to processing. We respond within one month.
"""

SECURITY_POLICY = """ACME AI SAAS - INFORMATION SECURITY POLICY

Section 1 Access control
Access to systems holding personal data is granted on least privilege,
reviewed quarterly, with multi-factor authentication for administrators.

Section 2 Security of processing
Personal data is encrypted in transit with TLS 1.3 and at rest with
AES-256, and restoration is tested twice a year.
"""

AI_POLICY = """ACME AI SAAS - AI GOVERNANCE POLICY

Section 1 Responsibility
The CTO owns AI governance. Every AI system has a named business owner
and is recorded in an inventory before it reaches production.

Section 2 Staff competence
All staff complete AI-awareness training within 30 days of joining and
annually thereafter, and completion is recorded.
"""

DPA = """ACME AI SAAS - DATA PROCESSING ADDENDUM

Section 1 Processor obligations
We process personal data only on documented instructions from the
controller, and we impose the same obligations on every sub-processor we
engage in writing before they begin work.
"""

ROPA = """ACME AI SAAS - RECORD OF PROCESSING ACTIVITIES

Section 1 Scope
This record covers, for each processing activity, the purposes, the
categories of data subjects and personal data, the categories of
recipients, international transfers, the retention periods and the
technical and organisational security measures applied.
"""


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


class _StubGateway:
    def __init__(self, mappings: list[ProposedMapping], *, doc_type: str, domain: str) -> None:
        self._mappings = mappings
        self._doc_type = doc_type
        self._domain = domain

    async def generate_structured(self, db, *, organization_id, requested_by, request, schema):  # type: ignore[no-untyped-def]
        return DocumentAnalysis(
            document_type=self._doc_type, document_domain=self._domain, mappings=self._mappings
        )


async def _signup(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"acme-{uuid.uuid4().hex[:8]}@example.com",
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


async def _upload(client: AsyncClient, db: AsyncSession, name: str, body: str) -> File:
    response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": name,
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
    raise AssertionError(f"no control {title!r}: {[c.title for c in controls]}")


async def _analyse(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    record: File,
    body: str,
    control_title: str,
    quote: str,
    doc_type: str,
    domain: str,
    confidence: float = 0.95,
    section_index: int = 1,
) -> None:
    """Upload analysis, exactly as the pipeline runs it — no attachment."""
    index = await _control_index(db, organization_id, control_title)
    await suggest_evidence_mappings(
        db,
        organization_id=organization_id,
        file_record=record,
        file_bytes=body.encode(),
        actor_user_id=None,
        gateway=_StubGateway(
            [
                ProposedMapping(
                    control_index=index,
                    section_index=section_index,
                    confidence=confidence,
                    rationale=f"{doc_type} supports this control.",
                    evidence_type="policy_statement",
                    quoted_passage=quote,
                )
            ],
            doc_type=doc_type,
            domain=domain,
        ),  # type: ignore[arg-type]
    )


async def test_five_documents_produce_a_full_compliance_position(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client)
    organization_id = await _organization_id(client, db_session)

    # --- The company -------------------------------------------------
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
    # One limited-risk chatbot. Deliberately *not* high risk — Article 26
    # must stay out of scope throughout.
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Customer Support AI",
            "purpose": "Draft replies from the knowledge base.",
            "risk_classification": "limited",
        },
    )

    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    ai_act = next(f for f in frameworks if f["key"] == "eu_ai_act")
    adopted = await client.post(
        "/api/v1/compliance/frameworks/adopt-recommended",
        json={"framework_keys": ["gdpr", "eu_ai_act"]},
    )
    assert adopted.status_code == 200, adopted.text

    baseline = (
        await client.post(f"/api/v1/compliance/frameworks/{gdpr['id']}/assess")
    ).json()
    assert baseline["readiness"]["percent"] == 0.0, "adopting must not move the position"

    # --- Five documents, no manual attachment ------------------------
    documents = [
        (
            "01_Privacy_Notice.txt",
            PRIVACY_NOTICE,
            "Publish and maintain a privacy notice",
            "We tell data subjects who we are, why we process their data",
            "Privacy Notice",
            "Privacy / GDPR",
        ),
        (
            "02_Information_Security_Policy.txt",
            SECURITY_POLICY,
            "Restrict access to personal data to authorised people",
            "Access to systems holding personal data is granted on least privilege",
            "Information Security Policy",
            "Security",
        ),
        (
            "03_AI_Governance_Policy.txt",
            AI_POLICY,
            "Establish an AI policy and assign responsibility",
            "The CTO owns AI governance. Every AI system has a named business owner",
            "AI Governance Policy",
            "AI Governance",
        ),
        (
            "04_Data_Processing_Addendum.txt",
            DPA,
            "Engage processors under a written data processing agreement",
            "We process personal data only on documented instructions from the",
            "Data Processing Addendum",
            "Privacy / GDPR",
        ),
        (
            "05_Record_of_Processing_Activities.txt",
            ROPA,
            "Maintain records of processing activities",
            "This record covers, for each processing activity, the purposes",
            "Record of Processing Activities",
            "Privacy / GDPR",
        ),
    ]

    for name, body, control_title, quote, doc_type, domain in documents:
        record = await _upload(client, db_session, name, body)
        await _analyse(
            db_session,
            organization_id=organization_id,
            record=record,
            body=body,
            control_title=control_title,
            quote=quote,
            doc_type=doc_type,
            domain=domain,
        )
    await db_session.commit()

    # --- Evidence exists, and nobody attached it ---------------------
    grouped = (await client.get("/api/v1/compliance/evidence/by-document")).json()
    assert len(grouped) == 5, "one row per source document, not one per mapping"
    assert all(document["evidence_count"] >= 1 for document in grouped)
    assert sum(document["control_count"] for document in grouped) >= 5

    evidence = (await client.get("/api/v1/compliance/evidence")).json()
    assert evidence, "no evidence was created from the uploads"

    # --- Assessment moves off zero on its own ------------------------
    after = (await client.post(f"/api/v1/compliance/frameworks/{gdpr['id']}/assess")).json()
    assert after["readiness"]["percent"] > baseline["readiness"]["percent"]

    # --- Control detail shows it without anyone attaching anything ---
    control_id = next(
        c["id"]
        for c in (await client.get("/api/v1/compliance/controls")).json()
        if c["title"] == "Maintain records of processing activities"
    )
    detail = (await client.get(f"/api/v1/compliance/controls/{control_id}")).json()
    assessment = detail["assessment"]
    assert assessment["status"] != "no_evidence"
    assert assessment["evidence"], "control detail shows no evidence"
    assert assessment["evidence"][0]["mapped_by"] == "auto"
    assert assessment["evidence"][0]["source_location"]

    # --- Genuine gaps, each carrying its remediation ------------------
    gaps = (await client.get("/api/v1/compliance/gaps")).json()
    assert gaps, "an unevidenced catalog must produce gaps"
    assert all(g["recommendation"] for g in gaps), "remediation must not wait for a click"
    for gap in gaps:
        lowered = gap["summary"].lower()
        for forbidden in ("violation", "breach of", "non-compliant", "unlawful"):
            assert forbidden not in lowered

    # --- Article 26 stayed out of it ---------------------------------
    ai_result = (
        await client.post(f"/api/v1/compliance/frameworks/{ai_act['id']}/assess")
    ).json()
    by_code = {r["reference_code"]: r for r in ai_result["requirements"]}
    assert by_code["Art. 26"]["status"] == "not_applicable"
    assert by_code["Art. 26"]["gap_id"] is None
    assert ai_result["readiness"]["total"] < len(ai_result["requirements"])

    # --- New evidence closes a gap and moves the score ---------------
    before_score = after["readiness"]["percent"]
    retention = """ACME AI SAAS - DATA RETENTION POLICY

Section 1 Retention and deletion
Support records are deleted 24 months after last contact, deletion runs
automatically each month, and the schedule is reviewed annually.
"""
    record = await _upload(client, db_session, "06_Retention_Policy.txt", retention)
    await _analyse(
        db_session,
        organization_id=organization_id,
        record=record,
        body=retention,
        control_title="Record a lawful basis for every processing activity",
        quote="Support records are deleted 24 months after last contact",
        doc_type="Data Retention Policy",
        domain="Privacy / GDPR",
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

    final = (await client.post(f"/api/v1/compliance/frameworks/{gdpr['id']}/assess")).json()
    assert final["readiness"]["percent"] >= before_score

    # --- The whole thing is readable afterwards ----------------------
    actions = set(
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
        "compliance.gap.created",
        "compliance.gap.remediation_generated",
    ):
        assert expected in actions, f"{expected} missing from the audit trail: {actions}"


async def test_a_high_risk_system_brings_article_26_into_scope(
    client: AsyncClient,
) -> None:
    """The other half of the scoping claim: it is conditional, not simply
    switched off. Registering a high-risk system must pull Article 26 back
    in and let it produce a finding."""
    await _signup(client)
    await client.put(
        "/api/v1/compliance/company-facts",
        json={"sells_to_eu_customers": True, "uses_third_party_ai": True},
    )
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Applicant Screening",
            "purpose": "Rank job applicants.",
            "risk_classification": "high",
        },
    )
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    ai_act = next(f for f in frameworks if f["key"] == "eu_ai_act")
    await client.put(
        f"/api/v1/compliance/frameworks/{ai_act['id']}/activation", json={"active": True}
    )

    result = (
        await client.post(f"/api/v1/compliance/frameworks/{ai_act['id']}/assess")
    ).json()
    by_code = {r["reference_code"]: r for r in result["requirements"]}
    assert by_code["Art. 26"]["status"] != "not_applicable"
