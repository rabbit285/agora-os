"""One logical document, however many times it is uploaded.

Four rows of one policy reached a real library, with 4, 5, 1 and 0
pieces of evidence and three different policy titles. Each row ran its
own extraction and the model proposes a slightly different set every
time — the diverging counts were the symptom, and the cause was that
they were ever separate documents.

The hole: the browser never sent a content hash, so every upload created
a row whose only identity was its filename, and the partial unique index
over `WHERE content_hash IS NOT NULL` correctly ignored all of them.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.document_dedupe import (
    choose_canonical,
    reconcile_documents,
)
from app.compliance.models import Evidence, EvidenceSuggestion, Policy
from app.core.dedupe import content_fingerprint
from app.core.models import File

POLICY = b"""Special Category Data Processing Policy

1. Purpose
This policy governs the processing of special category personal data.
"""
REVISED = POLICY + b"\n9. Review\nReviewed annually by the DPO.\n"


async def _signup(client: AsyncClient, email: str, org: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Dedupe Tester",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


def _file(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    name: str = "10_Special_Category_Data_Processing_Policy.docx",
    data: bytes = POLICY,
    content_hash: str | None = "",
    status: str = "ready",
) -> File:
    """A file row. `content_hash` defaults to the digest of `data`; pass
    None explicitly for a row that predates hashing.

    Reading the real bytes back from object storage — what the live
    backfill does — has nothing behind it here, so these fixtures start
    where the backfill leaves the library.
    """
    if content_hash == "":
        content_hash = content_fingerprint(data)
    return File(
        organization_id=org_id,
        storage_key=f"org/{org_id}/{uuid.uuid4()}/{name}",
        original_filename=name,
        content_type="text/plain",
        size_bytes=len(data),
        uploaded_by=user_id,
        processing_status=status,
        content_hash=content_hash,
    )


async def _files_in(db: AsyncSession, org_id: uuid.UUID, *, visible: bool = False) -> list[File]:
    stmt = select(File).where(File.organization_id == org_id)
    if visible:
        stmt = stmt.where(File.processing_status != "duplicate")
    return list((await db.execute(stmt.order_by(File.created_at))).scalars().all())


# --- the identity rules from the spec ---------------------------------


async def test_same_filename_same_bytes_is_one_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "dd-same@example.com", "Dedupe Same Org")
    digest = content_fingerprint(POLICY)
    db_session.add_all(
        [
            _file(org_id, user_id, content_hash=digest),
            _file(org_id, user_id, content_hash=digest),
        ]
    )
    await db_session.commit()

    await reconcile_documents(db_session, organization_id=org_id, dry_run=False)
    await db_session.commit()

    assert len(await _files_in(db_session, org_id, visible=True)) == 1
    # The row is kept, not deleted — somebody did upload it.
    assert len(await _files_in(db_session, org_id)) == 2


async def test_a_different_filename_with_the_same_bytes_is_still_one_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Identity is the content. A rename is not a new document."""
    user_id, org_id = await _signup(client, "dd-rename@example.com", "Dedupe Rename Org")
    digest = content_fingerprint(POLICY)
    db_session.add_all(
        [
            _file(org_id, user_id, name="policy.docx", content_hash=digest),
            _file(org_id, user_id, name="policy-final-v2-FINAL.docx", content_hash=digest),
        ]
    )
    await db_session.commit()

    await reconcile_documents(db_session, organization_id=org_id, dry_run=False)
    await db_session.commit()
    assert len(await _files_in(db_session, org_id, visible=True)) == 1


async def test_the_same_filename_with_different_bytes_stays_two_documents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A revised policy is a different document, and deduplication must
    not swallow a real edit."""
    user_id, org_id = await _signup(client, "dd-revised@example.com", "Dedupe Revised Org")
    db_session.add_all(
        [
            _file(org_id, user_id, content_hash=content_fingerprint(POLICY)),
            _file(org_id, user_id, data=REVISED, content_hash=content_fingerprint(REVISED)),
        ]
    )
    await db_session.commit()

    await reconcile_documents(db_session, organization_id=org_id, dry_run=False)
    await db_session.commit()
    assert len(await _files_in(db_session, org_id, visible=True)) == 2


async def test_identical_content_in_two_organizations_stays_two_documents(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tenant isolation is mandatory. Two customers holding the same
    published policy hold two documents."""
    user_a, org_a = await _signup(client, "dd-tenant-a@example.com", "Dedupe Tenant A")
    user_b, org_b = await _signup(client, "dd-tenant-b@example.com", "Dedupe Tenant B")
    digest = content_fingerprint(POLICY)
    db_session.add_all(
        [_file(org_a, user_a, content_hash=digest), _file(org_b, user_b, content_hash=digest)]
    )
    await db_session.commit()

    await reconcile_documents(db_session, dry_run=False)
    await db_session.commit()

    assert len(await _files_in(db_session, org_a, visible=True)) == 1
    assert len(await _files_in(db_session, org_b, visible=True)) == 1


async def test_a_file_uploaded_before_hashing_is_identified_from_its_bytes(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    """The actual hole. Every file uploaded before the hash column
    existed has none, and the partial unique index correctly ignores
    them — so two byte-identical rows coexisted and the duplicate check
    could not see the older one to match against it.
    """
    import app.core.storage as storage

    user_id, org_id = await _signup(client, "dd-prehash@example.com", "Dedupe Prehash Org")
    legacy = _file(org_id, user_id, content_hash=None)
    recent = _file(org_id, user_id, content_hash=content_fingerprint(POLICY))
    db_session.add_all([legacy, recent])
    await db_session.commit()

    monkeypatch.setattr(storage, "download_object", lambda key: POLICY)

    await reconcile_documents(db_session, organization_id=org_id, dry_run=False)
    await db_session.commit()

    visible = await _files_in(db_session, org_id, visible=True)
    assert len(visible) == 1
    # The older row is the document; the later one is the accident.
    assert visible[0].id == legacy.id
    assert visible[0].content_hash == content_fingerprint(POLICY)


# --- which row survives, and what it keeps ----------------------------


def test_the_canonical_document_is_the_earliest_finished_one() -> None:
    """Earliest because it is the row somebody may already have approved
    evidence against; finished because a half-processed row is not a
    result to adopt."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    org, user = uuid.uuid4(), uuid.uuid4()

    first = _file(org, user, status="failed")
    first.id, first.created_at = uuid.uuid4(), now
    second = _file(org, user, status="ready")
    second.id, second.created_at = uuid.uuid4(), now + timedelta(minutes=1)
    third = _file(org, user, status="ready")
    third.id, third.created_at = uuid.uuid4(), now + timedelta(minutes=2)

    # The failed one is older but was never a document.
    assert choose_canonical([first, second, third]) is second


async def test_a_human_approval_on_a_duplicate_is_carried_over_not_lost(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The one thing here that cannot be regenerated is a decision
    somebody made."""
    from app.compliance.models import Control

    user_id, org_id = await _signup(client, "dd-approval@example.com", "Dedupe Approval Org")
    canonical = _file(org_id, user_id, content_hash=content_fingerprint(POLICY))
    redundant = _file(org_id, user_id)
    only_here = Control(organization_id=org_id, title="Only the duplicate evidences this")
    db_session.add_all([canonical, redundant, only_here])
    await db_session.flush()

    db_session.add(
        EvidenceSuggestion(
            organization_id=org_id,
            file_id=redundant.id,
            control_id=only_here.id,
            status="approved",
            decided_by=user_id,
            quote_verified=True,
        )
    )
    db_session.add(
        Evidence(
            organization_id=org_id,
            file_id=redundant.id,
            control_id=only_here.id,
            title="Approved by a person",
        )
    )
    await db_session.commit()

    await reconcile_documents(db_session, organization_id=org_id, dry_run=False)
    await db_session.commit()

    # The evidence and the decision moved to the surviving document.
    moved = (
        await db_session.execute(
            select(Evidence).where(
                Evidence.file_id == canonical.id, Evidence.control_id == only_here.id
            )
        )
    ).scalars().first()
    assert moved is not None, "an approved piece of evidence was lost in the merge"

    decision = (
        await db_session.execute(
            select(EvidenceSuggestion).where(EvidenceSuggestion.file_id == canonical.id)
        )
    ).scalars().first()
    assert decision is not None
    assert decision.status == "approved"
    assert decision.decided_by == user_id


async def test_one_document_keeps_one_managed_policy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The screenshot showed three titles for one policy — one per
    duplicate row, each named by a separate classification run."""
    user_id, org_id = await _signup(client, "dd-policy@example.com", "Dedupe Policy Org")
    canonical = _file(org_id, user_id, content_hash=content_fingerprint(POLICY))
    redundant = _file(org_id, user_id)
    db_session.add_all([canonical, redundant])
    await db_session.flush()
    db_session.add_all(
        [
            Policy(
                organization_id=org_id,
                file_id=canonical.id,
                title="Special-Category Personal Data Processing Policy",
                status="needs_review",
            ),
            Policy(
                organization_id=org_id,
                file_id=redundant.id,
                title="Policy (Special-Category Personal Data Processing)",
                status="needs_review",
            ),
        ]
    )
    await db_session.commit()

    await reconcile_documents(db_session, organization_id=org_id, dry_run=False)
    await db_session.commit()

    live = (
        (
            await db_session.execute(
                select(Policy).where(
                    Policy.organization_id == org_id, Policy.status != "retired"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(live) == 1
    assert live[0].title == "Special-Category Personal Data Processing Policy"


async def test_the_copilot_stops_holding_the_same_passage_twice(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.knowledge.models import Document, DocumentChunk

    user_id, org_id = await _signup(client, "dd-chunks@example.com", "Dedupe Chunks Org")
    canonical = _file(org_id, user_id, content_hash=content_fingerprint(POLICY))
    redundant = _file(org_id, user_id)
    db_session.add_all([canonical, redundant])
    await db_session.flush()

    from app.knowledge.models import KnowledgeBase

    base = KnowledgeBase(organization_id=org_id, name=f"KB {uuid.uuid4().hex[:6]}")
    db_session.add(base)
    await db_session.flush()

    for file_record in (canonical, redundant):
        document = Document(
            organization_id=org_id,
            knowledge_base_id=base.id,
            file_id=file_record.id,
            title=file_record.original_filename,
            status="ready",
        )
        db_session.add(document)
        await db_session.flush()
        db_session.add(
            DocumentChunk(
                organization_id=org_id,
                document_id=document.id,
                chunk_index=0,
                content="This policy governs special category personal data.",
                embedding=[0.1, 0.2],
                token_count=10,
            )
        )
    await db_session.commit()

    before = int(
        (
            await db_session.execute(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.organization_id == org_id
                )
            )
        ).scalar_one()
    )
    assert before == 2

    await reconcile_documents(db_session, organization_id=org_id, dry_run=False)
    await db_session.commit()

    after = int(
        (
            await db_session.execute(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.organization_id == org_id
                )
            )
        ).scalar_one()
    )
    assert after == 1, "retrieval would still return the same passage twice"


# --- the operation is safe to repeat ----------------------------------


async def test_a_dry_run_changes_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The first thing anyone should do with a destructive cleanup is
    read it."""
    user_id, org_id = await _signup(client, "dd-dry@example.com", "Dedupe Dry Org")
    db_session.add_all(
        [
            _file(org_id, user_id, content_hash=content_fingerprint(POLICY)),
            _file(org_id, user_id),
        ]
    )
    await db_session.commit()

    report = await reconcile_documents(db_session, organization_id=org_id, dry_run=True)
    await db_session.commit()

    assert report.files_marked_duplicate == 1
    assert len(await _files_in(db_session, org_id, visible=True)) == 2


async def test_reconciling_twice_changes_nothing_the_second_time(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "dd-twice@example.com", "Dedupe Twice Org")
    db_session.add_all(
        [
            _file(org_id, user_id, content_hash=content_fingerprint(POLICY)),
            _file(org_id, user_id),
            _file(org_id, user_id),
        ]
    )
    await db_session.commit()

    first = await reconcile_documents(db_session, organization_id=org_id, dry_run=False)
    await db_session.commit()
    second = await reconcile_documents(db_session, organization_id=org_id, dry_run=False)
    await db_session.commit()

    assert first.files_marked_duplicate == 2
    assert second.files_marked_duplicate == 0, "the cleanup is not idempotent"
    assert len(await _files_in(db_session, org_id, visible=True)) == 1


# --- the library ------------------------------------------------------


async def test_the_documents_list_does_not_show_duplicate_markers(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The half-empty card in the screenshot — no classification, no
    evidence, no policy — was a duplicate marker rendered as a
    document."""
    user_id, org_id = await _signup(client, "dd-list@example.com", "Dedupe List Org")
    canonical = _file(org_id, user_id, content_hash=content_fingerprint(POLICY))
    db_session.add(canonical)
    await db_session.flush()
    marker = _file(org_id, user_id, status="duplicate")
    marker.duplicate_of_id = canonical.id
    db_session.add(marker)
    await db_session.commit()

    listed = (await client.get("/api/v1/compliance/documents")).json()
    ids = {row["id"] for row in listed}
    assert str(canonical.id) in ids
    assert str(marker.id) not in ids, "a duplicate marker rendered as a document"


async def test_uploading_the_same_bytes_twice_returns_the_document_already_held(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "dd-upload@example.com", "Dedupe Upload Org")
    digest = content_fingerprint(POLICY)
    db_session.add(_file(org_id, user_id, content_hash=digest))
    await db_session.commit()

    before = len(await _files_in(db_session, org_id))
    response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "renamed-copy.docx",
            "content_type": "text/plain",
            "size_bytes": len(POLICY),
            "content_hash": digest,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "duplicate"
    assert body["message"] == "This document has already been uploaded."
    assert body["upload_url"] is None
    assert len(await _files_in(db_session, org_id)) == before, "a File row was still created"


async def test_a_document_still_processing_does_not_start_a_second_pipeline(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "dd-inflight@example.com", "Dedupe Inflight Org")
    digest = content_fingerprint(POLICY)
    db_session.add(_file(org_id, user_id, content_hash=digest, status="analyzing"))
    await db_session.commit()

    response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": "10_Special_Category_Data_Processing_Policy.docx",
            "content_type": "text/plain",
            "size_bytes": len(POLICY),
            "content_hash": digest,
        },
    )
    body = response.json()
    assert body["status"] == "processing"
    assert body["message"] == "This document is already being processed."
    assert body["upload_url"] is None
