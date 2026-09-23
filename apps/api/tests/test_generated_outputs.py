"""What Veyntra produced, kept apart from what it was given.

A generated report is a result of compliance work, not an independent
source of it. That distinction did not exist, and the consequence was a
loop the product could walk on its own:

    evidence → assessment → audit → audit report → Documents →
    "Analyze for evidence" → evidence → assessment …

Once round that circle the compliance state is partly supported by a
document Veyntra wrote from the compliance state, and nothing in the
record says so.

These pin the fix at the level it has to hold: the type is stored on the
file, analysis refuses it, the copilot index skips it, and the one
legitimate exception — an audit report proving an audit happened —
refuses the case that would close the loop.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import artifacts, audit_state
from app.compliance.models import (
    Audit,
    AuditItem,
    AuditReport,
    Framework,
    Requirement,
    ReviewExport,
    SecurityReview,
)
from app.core.models import File


async def _signup(client: AsyncClient, email: str, org: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _completed_audit(
    db: AsyncSession, org_id: uuid.UUID, *, title: str = "ISO 42001 Internal Audit"
) -> tuple[Audit, Requirement]:
    framework = (
        await db.execute(select(Framework).where(Framework.key == "iso42001"))
    ).scalars().first()
    if framework is None:
        framework = Framework(key="iso42001", name="ISO 42001", description=None)
        db.add(framework)
        await db.flush()
    requirement = (
        await db.execute(
            select(Requirement).where(Requirement.framework_id == framework.id)
        )
    ).scalars().first()
    if requirement is None:
        requirement = Requirement(
            framework_id=framework.id,
            reference_code="9.2",
            title="Internal audit",
            description=None,
        )
        db.add(requirement)
        await db.flush()

    audit = Audit(
        organization_id=org_id,
        title=title,
        framework_id=framework.id,
        framework_name=framework.name,
        auditor_name="Zach Warren",
        auditor_type="internal",
        scope="AI governance controls and the evidence behind them.",
    )
    audit_state.apply_status(audit, "completed")
    db.add(audit)
    await db.flush()
    db.add(
        AuditItem(
            organization_id=org_id,
            audit_id=audit.id,
            requirement_id=requirement.id,
            reference_code=requirement.reference_code,
            requirement_title=requirement.title,
            framework_key="iso42001",
            control_title="Run internal audits at planned intervals",
            prepared_status="evidenced",
            decision="observation",
            evidence_snapshot=[],
        )
    )
    await db.flush()
    return audit, requirement


async def _uploader(db: AsyncSession, email: str) -> uuid.UUID:
    """The account that uploaded a fixture file.

    `files.uploaded_by` is a non-null foreign key, so this is looked up
    rather than invented.
    """
    from app.identity.models import User

    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalars().first()
    assert user is not None
    return user.id


def _uploaded(
    org_id: uuid.UUID,
    name: str = "Information Security Policy.docx",
    *,
    uploaded_by: uuid.UUID,
) -> File:
    return File(
        organization_id=org_id,
        storage_key=f"{org_id}/{uuid.uuid4()}",
        original_filename=name,
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        size_bytes=20_000,
        uploaded_by=uploaded_by,
    )


# --- classification -----------------------------------------------------


@pytest.mark.asyncio
async def test_a_generated_report_is_classified_at_generation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: the file the product writes says what it is.

    Classified by the generator rather than inferred afterwards, because
    the generator is the only place that knows for certain.
    """
    org_id = await _signup(client, "gen1@example.com", "Agora Origin")
    audit, _ = await _completed_audit(db_session, org_id)
    await db_session.commit()

    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    generated = await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report",
        json={"confirm_digest": preview["digest"]},
    )
    assert generated.status_code == 201, generated.text

    report = await db_session.get(AuditReport, uuid.UUID(generated.json()["id"]))
    file_record = await db_session.get(File, report.file_id)
    assert artifacts.is_generated(file_record)
    assert file_record.artifact_type == "generated_output"
    assert file_record.origin_type == "audit_report"
    # The audit, not the report row — this is what the link opens and
    # what the circularity check reasons about.
    assert file_record.origin_id == audit.id
    assert file_record.origin_label == "ISO 42001 Internal Audit"
    # Never "not analyzed", which is what put "Analyze for evidence" on
    # every report the product wrote.
    assert file_record.processing_status == "generated"


@pytest.mark.asyncio
async def test_an_uploaded_document_stays_a_source_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19: the existing evidence workflow is untouched."""
    org_id = await _signup(client, "gen2@example.com", "Agora Origin")
    file_record = _uploaded(
        org_id, uploaded_by=await _uploader(db_session, "gen2@example.com")
    )
    db_session.add(file_record)
    await db_session.commit()

    assert file_record.artifact_type == "source"
    assert artifacts.is_generated(file_record) is False
    assert file_record.origin_type is None
    # And analysis is still offered.
    await artifacts.guard_analysis(file_record)


@pytest.mark.asyncio
async def test_the_document_library_lists_the_two_kinds_apart(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4: a report and a policy stopped looking identical."""
    org_id = await _signup(client, "gen3@example.com", "Agora Origin")
    audit, _ = await _completed_audit(db_session, org_id)
    db_session.add(
        _uploaded(org_id, uploaded_by=await _uploader(db_session, "gen3@example.com"))
    )
    await db_session.commit()

    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    await client.post(
        f"/api/v1/compliance/audits/{audit.id}/report",
        json={"confirm_digest": preview["digest"]},
    )

    documents = (await client.get("/api/v1/compliance/documents")).json()
    kinds = {doc["original_filename"]: doc for doc in documents}

    policy = kinds["Information Security Policy.docx"]
    assert policy["artifact_type"] == "source"
    assert policy["artifact_label"] == "Source document"
    assert policy["origin_href"] is None

    report = next(
        doc for doc in documents if doc["artifact_type"] == "generated_output"
    )
    assert report["artifact_label"] == "Generated output"
    assert report["origin_label"] == "ISO 42001 Internal Audit"
    # §5: navigable back to the record it came out of.
    assert report["origin_href"] == f"/compliance/audits/{audit.id}"
    assert report["processing_status"] == "generated"


# --- evidence analysis --------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_analysis_refuses_a_generated_report(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2/§3: the click that closed the loop.

    Refused at the endpoint rather than filtered in a query, so whoever
    asked is told why instead of watching a request come back empty.
    """
    org_id = await _signup(client, "gen4@example.com", "Agora Origin")
    audit, _ = await _completed_audit(db_session, org_id)
    await db_session.commit()

    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    generated = (
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/report",
            json={"confirm_digest": preview["digest"]},
        )
    ).json()
    report = await db_session.get(AuditReport, uuid.UUID(generated["id"]))

    refused = await client.post(
        "/api/v1/compliance/evidence/analyze",
        json={"file_id": str(report.file_id)},
    )
    assert refused.status_code == 422
    body = refused.text
    assert "generated by Veyntra" in body
    # The reason is the point: it explains the circularity rather than
    # just declining.
    assert "supported by a document written from that same state" in body


@pytest.mark.asyncio
async def test_a_security_review_export_is_not_evidence_either(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§11/§18: the same rule for customer-facing deliverables."""
    org_id = await _signup(client, "gen5@example.com", "Agora Origin")
    review = SecurityReview(
        organization_id=org_id,
        title="Agora Origin Security Review",
        customer_name="Customer A",
    )
    db_session.add(review)
    await db_session.flush()

    file_record = _uploaded(
        org_id,
        "Security Review Summary.pdf",
        uploaded_by=await _uploader(db_session, "gen5@example.com"),
    )
    db_session.add(file_record)
    await db_session.flush()
    export = ReviewExport(
        organization_id=org_id,
        security_review_id=review.id,
        output_type="summary",
        file_format="pdf",
        title="Security Review Summary",
        version=1,
        file_id=file_record.id,
        contents={},
    )
    db_session.add(export)
    await db_session.flush()

    # Backfill classifies it from the generation record, not the name.
    counts = await artifacts.backfill(db_session)
    await db_session.commit()
    assert counts["review_exports"] == 1

    await db_session.refresh(file_record)
    assert file_record.artifact_type == "generated_output"
    assert file_record.origin_type == "review_export"
    assert file_record.origin_label == "Agora Origin Security Review"

    refused = await client.post(
        "/api/v1/compliance/evidence/analyze",
        json={"file_id": str(file_record.id)},
    )
    assert refused.status_code == 422


# --- circular evidence --------------------------------------------------


@pytest.mark.asyncio
async def test_a_report_cannot_evidence_the_requirements_its_audit_assessed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10/§20: the specific loop, refused specifically.

    The report says the requirement is met *because the auditor
    concluded so*. Feeding that back as independent evidence launders a
    conclusion into a fact.
    """
    org_id = await _signup(client, "gen6@example.com", "Agora Origin")
    audit, requirement = await _completed_audit(db_session, org_id)
    await db_session.commit()

    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    generated = (
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/report",
            json={"confirm_digest": preview["digest"]},
        )
    ).json()
    report = await db_session.get(AuditReport, uuid.UUID(generated["id"]))
    file_record = await db_session.get(File, report.file_id)

    circular = await artifacts.check_circularity(
        db_session, file_record=file_record, requirement_id=requirement.id
    )
    assert circular.circular is True
    assert "written from the conclusion about it" in circular.reason


@pytest.mark.asyncio
async def test_a_report_may_evidence_a_requirement_its_audit_did_not_assess(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9: the exception is real and narrow.

    "Perform internal audits" is a requirement an audit report genuinely
    proves — as long as it is not one that audit itself concluded on.
    """
    org_id = await _signup(client, "gen7@example.com", "Agora Origin")
    audit, _ = await _completed_audit(db_session, org_id)
    other = Requirement(
        framework_id=audit.framework_id,
        reference_code="OTHER-1",
        title="A requirement this audit never looked at",
        description=None,
    )
    db_session.add(other)
    await db_session.commit()

    preview = (
        await client.post(f"/api/v1/compliance/audits/{audit.id}/report/preview")
    ).json()
    generated = (
        await client.post(
            f"/api/v1/compliance/audits/{audit.id}/report",
            json={"confirm_digest": preview["digest"]},
        )
    ).json()
    report = await db_session.get(AuditReport, uuid.UUID(generated["id"]))
    file_record = await db_session.get(File, report.file_id)

    allowed = await artifacts.check_circularity(
        db_session, file_record=file_record, requirement_id=other.id
    )
    assert allowed.circular is False

    # And an uploaded document is never circular.
    upload = _uploaded(
        org_id, uploaded_by=await _uploader(db_session, "gen7@example.com")
    )
    db_session.add(upload)
    await db_session.flush()
    assert (
        await artifacts.check_circularity(
            db_session, file_record=upload, requirement_id=other.id
        )
    ).circular is False


# --- copilot ------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_copilot_index_skips_generated_output(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8/§21: "Are we compliant?" must not be answered from a report
    Veyntra wrote about whether we are compliant."""
    from app.compliance import copilot_index

    org_id = await _signup(client, "gen8@example.com", "Agora Origin")

    uploader = await _uploader(db_session, "gen8@example.com")
    source = _uploaded(org_id, uploaded_by=uploader)
    source.processing_status = "ready"
    source.index_status = "pending"
    generated = _uploaded(
        org_id, "ISO 42001 Internal Audit v1.pdf", uploaded_by=uploader
    )
    # The shape a report would be in if something had marked it ready.
    generated.processing_status = "ready"
    generated.index_status = "pending"
    generated.artifact_type = "generated_output"
    generated.origin_type = "audit_report"
    db_session.add_all([source, generated])
    await db_session.commit()

    pending = list(
        (
            await db_session.execute(
                select(File).where(
                    File.organization_id == org_id,
                    File.processing_status == "ready",
                    File.index_status.in_(("pending", "failed")),
                    File.artifact_type == "source",
                )
            )
        )
        .scalars()
        .all()
    )
    assert [row.original_filename for row in pending] == [
        "Information Security Policy.docx"
    ]
    assert copilot_index is not None


# --- migration ----------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_uses_generation_records_not_filenames(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§16: a customer can upload something called "Audit Report v2".

    Reclassifying it on the strength of its name would quietly drop a
    real document out of the evidence library.
    """
    org_id = await _signup(client, "gen9@example.com", "Agora Origin")
    audit, _ = await _completed_audit(db_session, org_id)

    # A real generated file, recorded the old way: classified as source.
    uploader = await _uploader(db_session, "gen9@example.com")
    real = _uploaded(
        org_id, "ISO 42001 Internal Audit v1.pdf", uploaded_by=uploader
    )
    db_session.add(real)
    await db_session.flush()
    db_session.add(
        AuditReport(
            organization_id=org_id,
            audit_id=audit.id,
            title="ISO 42001 Internal Audit — Internal Audit Report",
            version=1,
            file_id=real.id,
            contents={"audit_title": "ISO 42001 Internal Audit"},
        )
    )

    # And an upload that merely looks like one.
    decoy = _uploaded(org_id, "Audit Report v2.pdf", uploaded_by=uploader)
    decoy.processing_status = "ready"
    db_session.add(decoy)
    await db_session.commit()

    counts = await artifacts.backfill(db_session)
    await db_session.commit()
    assert counts["audit_reports"] == 1

    await db_session.refresh(real)
    await db_session.refresh(decoy)
    assert real.artifact_type == "generated_output"
    assert real.origin_label == "ISO 42001 Internal Audit"
    # The lookalike is untouched, and still analysable.
    assert decoy.artifact_type == "source"
    assert decoy.processing_status == "ready"
    await artifacts.guard_analysis(decoy)


@pytest.mark.asyncio
async def test_backfill_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "gen10@example.com", "Agora Origin")
    audit, _ = await _completed_audit(db_session, org_id)
    file_record = _uploaded(
        org_id,
        "ISO 42001 Internal Audit v1.pdf",
        uploaded_by=await _uploader(db_session, "gen10@example.com"),
    )
    db_session.add(file_record)
    await db_session.flush()
    db_session.add(
        AuditReport(
            organization_id=org_id,
            audit_id=audit.id,
            title="Report",
            version=1,
            file_id=file_record.id,
            contents={},
        )
    )
    await db_session.commit()

    first = await artifacts.backfill(db_session)
    await db_session.commit()
    second = await artifacts.backfill(db_session)
    await db_session.commit()

    assert first["audit_reports"] == 1
    assert second["audit_reports"] == 0
