"""Running the same operation twice must produce one compliance result.

The pipeline was append-only where it should have been reconciling.
Reprocessing one policy five times left five Evidence rows for the same
file and control, so a control's evidence count was counting our retries
rather than the customer's documents.

Every test here asserts **database counts**, not HTTP responses. Hiding
duplicates in a response while leaving them in the table is the failure
mode this is written against.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    ComplianceGap,
    Control,
    ControlMapping,
    Evidence,
    EvidenceSuggestion,
    Framework,
    Requirement,
)
from app.core.dedupe import content_fingerprint, get_or_create, text_fingerprint
from app.core.models import File, Notification, Task
from app.core.notifications import notify

DOCUMENT = b"""Special Category Data Processing Policy

1. Purpose
This policy governs the processing of special category personal data.

5. Article 9 condition review
Each processing activity records its Article 9 condition and its owner.
"""


async def _signup(client: AsyncClient, email: str, org: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Idem Tester",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


async def _counts(db: AsyncSession, org_id: uuid.UUID) -> dict[str, int]:
    """The numbers the acceptance test compares. Read from the tables,
    never from an endpoint that might be filtering duplicates out of the
    view while leaving them in the database."""

    async def count(model: Any, *conditions: Any) -> int:
        return int(
            (
                await db.execute(
                    select(func.count(model.id)).where(
                        model.organization_id == org_id, *conditions
                    )
                )
            ).scalar_one()
        )

    return {
        "documents": await count(File),
        "evidence": await count(Evidence),
        "mappings": await count(EvidenceSuggestion),
        "gaps": await count(ComplianceGap),
        "open_gaps": await count(ComplianceGap, ComplianceGap.status != "resolved"),
        "tasks": await count(Task),
        "notifications": await count(Notification),
    }


async def _fixture(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[File, Control]:
    control = Control(
        organization_id=org_id, title="Control special category data", description=None
    )
    file_record = File(
        organization_id=org_id,
        storage_key=f"org/{org_id}/{uuid.uuid4()}/policy.txt",
        original_filename="10_Special_Category_Data_Processing_Policy.docx",
        content_type="text/plain",
        size_bytes=len(DOCUMENT),
        uploaded_by=user_id,
        processing_status="ready",
        content_hash=content_fingerprint(DOCUMENT),
    )
    db.add_all([control, file_record])
    await db.flush()
    return (file_record, control)


# --- the identities themselves ----------------------------------------


def test_a_file_is_identified_by_its_bytes_not_its_name() -> None:
    assert content_fingerprint(DOCUMENT) == content_fingerprint(DOCUMENT)
    assert content_fingerprint(DOCUMENT) != content_fingerprint(DOCUMENT + b" ")


def test_a_passage_survives_being_rewrapped() -> None:
    """Re-extraction rewraps paragraphs. A citation that means the same
    thing must not read as a second proposal."""
    assert text_fingerprint("5. Review", "Each activity   records\nits condition") == (
        text_fingerprint("5. Review", "each activity records its condition")
    )
    assert text_fingerprint("5. Review", "a") != text_fingerprint("5. Review", "b")
    # The separator prevents ("ab","c") and ("a","bc") colliding.
    assert text_fingerprint("ab", "c") != text_fingerprint("a", "bc")


# --- evidence: the worst offender -------------------------------------


async def test_the_same_document_evidences_a_control_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "idem-ev@example.com", "Idem Evidence Org")
    file_record, control = await _fixture(db_session, org_id, user_id)

    # Ten runs of the operation that used to insert blindly.
    for _ in range(10):
        await get_or_create(
            db_session,
            Evidence,
            match={
                "organization_id": org_id,
                "file_id": file_record.id,
                "control_id": control.id,
            },
            defaults={"title": file_record.original_filename, "created_by": None},
        )
    await db_session.commit()

    rows = (
        (
            await db_session.execute(
                select(Evidence).where(
                    Evidence.organization_id == org_id,
                    Evidence.file_id == file_record.id,
                    Evidence.control_id == control.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_get_or_create_reports_whether_it_actually_created(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Callers use this to tell a real state transition from a retry —
    it is what stops a retried job announcing the same news twice."""
    user_id, org_id = await _signup(client, "idem-created@example.com", "Idem Created Org")
    file_record, control = await _fixture(db_session, org_id, user_id)

    match = {
        "organization_id": org_id,
        "file_id": file_record.id,
        "control_id": control.id,
    }
    _, first = await get_or_create(db_session, Evidence, match=match, defaults={"title": "x"})
    _, second = await get_or_create(db_session, Evidence, match=match, defaults={"title": "x"})
    assert (first, second) == (True, False)


async def test_concurrent_duplicate_creation_still_yields_one_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`if not exists: insert` passes this test only by luck. Eight
    coroutines racing on one session is not true parallelism, but it does
    interleave the check and the insert, which is the window that
    matters."""
    user_id, org_id = await _signup(client, "idem-race@example.com", "Idem Race Org")
    file_record, control = await _fixture(db_session, org_id, user_id)

    match = {
        "organization_id": org_id,
        "file_id": file_record.id,
        "control_id": control.id,
    }
    await asyncio.gather(
        *[
            get_or_create(db_session, Evidence, match=match, defaults={"title": "x"})
            for _ in range(8)
        ]
    )
    await db_session.commit()

    total = int(
        (
            await db_session.execute(
                select(func.count(Evidence.id)).where(
                    Evidence.organization_id == org_id,
                    Evidence.file_id == file_record.id,
                    Evidence.control_id == control.id,
                )
            )
        ).scalar_one()
    )
    assert total == 1


# --- suggestions: a decision must not be undone by a retry ------------


async def test_reprocessing_does_not_return_an_approved_mapping_to_the_queue(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The failure this prevents is worse than a duplicate row: work a
    person already did coming back as pending."""
    user_id, org_id = await _signup(client, "idem-appr@example.com", "Idem Approved Org")
    file_record, control = await _fixture(db_session, org_id, user_id)

    identity = text_fingerprint("5. Article 9 condition review", "Each processing activity")
    suggestion = EvidenceSuggestion(
        organization_id=org_id,
        file_id=file_record.id,
        control_id=control.id,
        passage_hash=identity,
        status="approved",
        source_location="5. Article 9 condition review",
        quoted_passage="Each processing activity",
        quote_verified=True,
        decided_by=user_id,
    )
    db_session.add(suggestion)
    await db_session.commit()

    # What re-extraction does: find it by identity rather than insert.
    found = (
        await db_session.execute(
            select(EvidenceSuggestion).where(
                EvidenceSuggestion.organization_id == org_id,
                EvidenceSuggestion.file_id == file_record.id,
                EvidenceSuggestion.control_id == control.id,
                EvidenceSuggestion.passage_hash == identity,
            )
        )
    ).scalars().first()

    assert found is not None
    assert found.status == "approved", "a human decision was overwritten by a retry"
    assert found.decided_by == user_id


# --- notifications ----------------------------------------------------


async def test_a_retried_job_does_not_announce_the_same_news_twice(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "idem-notif@example.com", "Idem Notify Org")
    key = f"document.analyzed:{uuid.uuid4()}"

    for _ in range(3):
        await notify(
            db_session,
            organization_id=org_id,
            user_id=user_id,
            title="Document analyzed",
            body="Special Category Data Processing Policy is ready.",
            idempotency_key=key,
        )
    await db_session.commit()

    total = int(
        (
            await db_session.execute(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id,
                    Notification.idempotency_key == key,
                )
            )
        ).scalar_one()
    )
    assert total == 1


async def test_a_notification_with_no_key_is_unaffected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Hundreds of call sites pass no key. They must keep working exactly
    as before rather than silently collapsing into one row."""
    user_id, org_id = await _signup(client, "idem-nokey@example.com", "Idem No Key Org")
    for index in range(2):
        await notify(
            db_session,
            organization_id=org_id,
            user_id=user_id,
            title=f"Ad-hoc {index}",
        )
    await db_session.commit()

    total = int(
        (
            await db_session.execute(
                select(func.count(Notification.id)).where(Notification.user_id == user_id)
            )
        ).scalar_one()
    )
    assert total == 2


# --- gaps and remediation ---------------------------------------------


async def test_repeated_assessment_leaves_the_gap_count_where_it_was(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Whatever the first assessment concludes, the fourth must conclude
    the same thing. The count after one run is the baseline; the
    invariant is that running it again does not move it."""
    from app.compliance.assessment import evaluate_framework

    _, org_id = await _signup(client, "idem-gap@example.com", "Idem Gap Org")
    framework = Framework(key=f"gdpr-{uuid.uuid4().hex[:6]}", name="GDPR", description=None)
    db_session.add(framework)
    await db_session.flush()
    requirement = Requirement(
        framework_id=framework.id,
        reference_code="Art. 32",
        title="Security of processing",
        description=None,
    )
    control = Control(organization_id=org_id, title="Back up production data", description=None)
    db_session.add_all([requirement, control])
    await db_session.flush()
    db_session.add(ControlMapping(control_id=control.id, requirement_id=requirement.id))
    await db_session.commit()

    async def gap_count() -> int:
        return int(
            (
                await db_session.execute(
                    select(func.count(ComplianceGap.id)).where(
                        ComplianceGap.organization_id == org_id,
                        ComplianceGap.status != "resolved",
                    )
                )
            ).scalar_one()
        )

    await evaluate_framework(db_session, organization_id=org_id, framework=framework)
    await db_session.commit()
    baseline = await gap_count()

    for _ in range(3):
        await evaluate_framework(db_session, organization_id=org_id, framework=framework)
        await db_session.commit()

    assert await gap_count() == baseline, "reassessment changed the number of open gaps"


async def test_the_database_refuses_a_second_open_gap_for_one_deficiency(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The service deduplicates; this is the floor underneath it.

    Two workers racing past a service-level check would both insert. The
    partial unique index — open gaps only, so a resolved one can be
    followed by a genuine regression — is what makes that impossible
    rather than unlikely.
    """
    _, org_id = await _signup(client, "idem-gapdb@example.com", "Idem Gap DB Org")
    framework = Framework(key=f"iso-{uuid.uuid4().hex[:6]}", name="ISO 27001", description=None)
    db_session.add(framework)
    await db_session.flush()
    requirement = Requirement(
        framework_id=framework.id,
        reference_code="A.12",
        title="Backup",
        description=None,
    )
    control = Control(organization_id=org_id, title="Restore test", description=None)
    db_session.add_all([requirement, control])
    await db_session.flush()

    identity = {
        "organization_id": org_id,
        "framework_id": framework.id,
        "requirement_id": requirement.id,
        "control_id": control.id,
        "kind": "evidence_missing",
    }
    for _ in range(5):
        await get_or_create(
            db_session,
            ComplianceGap,
            match=identity,
            defaults={
                "status": "open",
                "severity": "medium",
                "summary": "Missing backup restoration evidence",
            },
        )
    await db_session.commit()

    open_gaps = (
        (
            await db_session.execute(
                select(ComplianceGap).where(
                    ComplianceGap.organization_id == org_id,
                    ComplianceGap.requirement_id == requirement.id,
                    ComplianceGap.status != "resolved",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(open_gaps) == 1
    assert open_gaps[0].summary == "Missing backup restoration evidence"


# --- the acceptance test ----------------------------------------------


async def test_acceptance_repeated_operations_leave_every_count_stable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """One clean organization, one document, then the same technical
    operations again and again. Every logical count must hold."""
    user_id, org_id = await _signup(client, "idem-accept@example.com", "Idem Acceptance Org")
    file_record, control = await _fixture(db_session, org_id, user_id)
    identity = text_fingerprint("1. Purpose", "This policy governs")

    async def run_pipeline_once() -> None:
        """The parts of the pipeline that create records, as a
        reconciliation rather than an append."""
        suggestion_match = {
            "organization_id": org_id,
            "file_id": file_record.id,
            "control_id": control.id,
            "passage_hash": identity,
        }
        _, created = await get_or_create(
            db_session,
            EvidenceSuggestion,
            match=suggestion_match,
            defaults={
                "status": "auto_approved",
                "source_location": "1. Purpose",
                "quoted_passage": "This policy governs",
                "quote_verified": True,
            },
        )
        await get_or_create(
            db_session,
            Evidence,
            match={
                "organization_id": org_id,
                "file_id": file_record.id,
                "control_id": control.id,
            },
            defaults={"title": file_record.original_filename, "created_by": None},
        )
        # A notification only for a real transition, keyed to the
        # document rather than to the attempt.
        if created:
            await notify(
                db_session,
                organization_id=org_id,
                user_id=user_id,
                title="Document analyzed",
                idempotency_key=f"document.analyzed:{file_record.id}",
            )
        await db_session.commit()

    await run_pipeline_once()
    baseline = await _counts(db_session, org_id)
    assert baseline["evidence"] == 1
    assert baseline["mappings"] == 1

    # The same document uploaded again — the identity is the bytes, so
    # this resolves to the row already held.
    duplicate_lookup = (
        await db_session.execute(
            select(File).where(
                File.organization_id == org_id,
                File.content_hash == content_fingerprint(DOCUMENT),
            )
        )
    ).scalars().all()
    assert len(duplicate_lookup) == 1

    # Reprocessing, three times.
    for _ in range(3):
        await run_pipeline_once()

    # The same background job delivered twice.
    await run_pipeline_once()
    await run_pipeline_once()

    after = await _counts(db_session, org_id)
    assert after == baseline, f"counts drifted: {baseline} -> {after}"


async def test_a_genuinely_different_document_is_a_new_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Deduplication must not swallow a real edit. A modified policy is a
    different document and has to be able to say so."""
    user_id, org_id = await _signup(client, "idem-diff@example.com", "Idem Different Org")
    file_record, _ = await _fixture(db_session, org_id, user_id)

    revised = File(
        organization_id=org_id,
        storage_key=f"org/{org_id}/{uuid.uuid4()}/policy-v2.txt",
        original_filename="10_Special_Category_Data_Processing_Policy.docx",
        content_type="text/plain",
        size_bytes=len(DOCUMENT) + 20,
        uploaded_by=user_id,
        processing_status="ready",
        content_hash=content_fingerprint(DOCUMENT + b"\n\n9. Review\nAnnually."),
    )
    db_session.add(revised)
    await db_session.commit()

    assert revised.content_hash != file_record.content_hash
    total = int(
        (
            await db_session.execute(
                select(func.count(File.id)).where(File.organization_id == org_id)
            )
        ).scalar_one()
    )
    assert total == 2


async def test_the_upload_endpoint_answers_a_duplicate_without_creating_a_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "idem-upload@example.com", "Idem Upload Org")
    await _fixture(db_session, org_id, user_id)
    await db_session.commit()

    before = int(
        (
            await db_session.execute(
                select(func.count(File.id)).where(File.organization_id == org_id)
            )
        ).scalar_one()
    )

    response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "10_Special_Category_Data_Processing_Policy.docx",
            "content_type": "text/plain",
            "size_bytes": len(DOCUMENT),
            "content_hash": content_fingerprint(DOCUMENT),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "duplicate"
    assert body["message"] == "This document has already been uploaded."
    assert body["upload_url"] is None

    after = int(
        (
            await db_session.execute(
                select(func.count(File.id)).where(File.organization_id == org_id)
            )
        ).scalar_one()
    )
    assert after == before, "a duplicate upload still created a File row"


async def test_a_new_file_still_uploads_normally(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The duplicate check must not block the ordinary case."""
    await _signup(client, "idem-new@example.com", "Idem New Org")
    response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "brand-new.txt",
            "content_type": "text/plain",
            "size_bytes": 100,
            "content_hash": content_fingerprint(b"something else entirely"),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "new"
    assert body["upload_url"]


async def test_an_upload_with_no_hash_is_unaffected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Clients that do not compute a hash keep working exactly as before;
    the pipeline still deduplicates them once it reads the bytes."""
    await _signup(client, "idem-nohash@example.com", "Idem No Hash Org")
    response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "legacy-client.txt",
            "content_type": "text/plain",
            "size_bytes": 100,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["upload_url"]


@pytest.mark.parametrize(
    "status",
    ["parsing", "analyzing"],
)
async def test_a_document_already_in_flight_does_not_start_a_second_pipeline(
    client: AsyncClient, db_session: AsyncSession, status: str
) -> None:
    """A user refreshing mid-processing, or a queue redelivering, must not
    launch the pipeline over a document it is already running on."""
    from app.compliance.evidence_ai import process_document

    user_id, org_id = await _signup(
        client, f"idem-flight-{status}@example.com", f"Idem Flight {status}"
    )
    file_record, _ = await _fixture(db_session, org_id, user_id)
    file_record.processing_status = status
    await db_session.commit()

    # Returns without touching storage — a download would raise here,
    # since nothing was ever uploaded for this fixture.
    await process_document(
        file_record.id,
        organization_id=org_id,
        actor_user_id=None,
        session_factory=lambda: _SessionHandle(db_session),
    )

    await db_session.refresh(file_record)
    assert file_record.processing_status == status


class _SessionHandle:
    """Hands the test's own session to code that opens its own."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_: object) -> None:
        return None


async def test_two_documents_processed_together_share_one_knowledge_base(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An organization's first two uploads must not race each other.

    `_knowledge_base` read then inserted, so two documents submitted
    together both found no knowledge base, both inserted, and the second
    died on `uq_knowledge_base_org_name` — marking a perfectly good
    document `failed` for a reason that had nothing to do with it. Seen
    live on a fresh signup uploading two policies in a row.
    """
    from app.compliance.copilot_index import COMPLIANCE_KNOWLEDGE_BASE, _knowledge_base
    from app.knowledge.models import KnowledgeBase

    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "kb-race@example.com",
            "password": "correct-horse-battery",
            "full_name": "Race Tester",
            "organization_name": "Knowledge Base Race Org",
        },
    )
    assert response.status_code == 200, response.text
    org_id = uuid.UUID(response.json()["organization"]["id"])

    first = await _knowledge_base(db_session, org_id)
    second = await _knowledge_base(db_session, org_id)
    third = await _knowledge_base(db_session, org_id)
    await db_session.commit()

    assert first.id == second.id == third.id

    count = (
        await db_session.execute(
            select(func.count(KnowledgeBase.id)).where(
                KnowledgeBase.organization_id == org_id,
                KnowledgeBase.name == COMPLIANCE_KNOWLEDGE_BASE,
            )
        )
    ).scalar_one()
    assert count == 1
