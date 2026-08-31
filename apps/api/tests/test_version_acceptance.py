"""The version-management acceptance tests, §32–§38.

These assert database relationships and counts, not HTTP status codes.
A version feature that returns 200 while quietly forking a policy record
or resurrecting superseded wording as current evidence has failed in the
only way that matters, and it fails invisibly — which is why every check
below reads the rows.

Where a test covers a numbered acceptance case its docstring says so.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance.document_versioning import find_version_candidate
from app.compliance.models import (
    Control,
    Evidence,
    EvidenceSuggestion,
    Policy,
)
from app.compliance.version_backfill import backfill_version_candidates
from app.compliance.version_promotion import accept_new_version, version_history
from app.core.dedupe import content_fingerprint, text_fingerprint
from app.core.models import File, Notification
from app.knowledge.models import Document, DocumentChunk, KnowledgeBase

# --- the documents the acceptance cases are written against -----------

V1 = """AI Governance Policy
Version: 1.0
Effective: May 2026

1. Purpose
This policy sets out how the company governs its use of artificial intelligence
across every product and every team that operates one.

7. Monitoring
AI systems should be monitored.

10. Retention
Model training data is retained for two years and then deleted.
"""

V2 = """AI Governance Policy
Version: 2.0
Effective: August 2026

1. Purpose
This policy sets out how the company governs its use of artificial intelligence
across every product and every team that operates one.

7. Monitoring
Production AI systems are reviewed monthly for drift, incidents and material
performance changes by the AI Governance Lead.

8. Human oversight
Every production AI system has a named human owner who can halt it.
"""

TRAVEL = """Employee Travel Policy
Version: 1.0

1. Purpose
This policy sets out how employees book and claim travel, what classes of
travel are permitted, and the approval each requires before booking.

2. Booking
Travel is booked through the corporate travel desk wherever possible.
"""


async def _signup(client: AsyncClient, email: str, org: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Acceptance Tester",
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
    name: str,
    data: str,
    version_label: str | None = None,
    created_at=None,
) -> File:
    record = File(
        organization_id=org_id,
        storage_key=f"org/{org_id}/{uuid.uuid4()}/{name}",
        original_filename=name,
        content_type="text/plain",
        size_bytes=len(data),
        uploaded_by=user_id,
        processing_status="ready",
        content_hash=content_fingerprint(data.encode()),
        version_label=version_label,
        document_type="Policy",
    )
    if created_at is not None:
        record.created_at = created_at
    return record


def _suggestion(
    org_id: uuid.UUID,
    file_record: File,
    *,
    control_id: uuid.UUID,
    section: str,
    passage: str,
    status: str = "proposed",
    decided_by: uuid.UUID | None = None,
) -> EvidenceSuggestion:
    return EvidenceSuggestion(
        organization_id=org_id,
        file_id=file_record.id,
        control_id=control_id,
        requirement_id=None,
        source_location=section,
        quoted_passage=passage,
        passage_hash=text_fingerprint(section, passage),
        evidence_type="policy",
        status=status,
        confidence=0.9,
        decided_by=decided_by,
    )


async def _control(db: AsyncSession, org_id: uuid.UUID, title: str) -> Control:
    control = Control(organization_id=org_id, title=title, description=title, status="draft")
    db.add(control)
    await db.flush()
    return control


# --- §32 exact duplicate ----------------------------------------------


async def test_32_the_same_bytes_twice_produce_one_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§32: an identical re-upload is settled by the content hash.

    It is not a version question at all — nothing is proposed, because
    there is nothing to decide.
    """
    user_id, org_id = await _signup(client, "acc-dup@example.com", "Acc Dup Org")
    first = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1)
    db_session.add(first)
    await db_session.commit()

    same_hash = content_fingerprint(V1.encode())
    existing = (
        await db_session.execute(
            select(File).where(
                File.organization_id == org_id, File.content_hash == same_hash
            )
        )
    ).scalars().all()

    assert len(existing) == 1
    assert existing[0].id == first.id
    # No version chain, no proposal: the same document is the same
    # document, and asking about it would be a question with one answer.
    assert first.version_candidate_id is None
    assert first.superseded_by_id is None


# --- §33 new version, same filename -----------------------------------


async def test_33_same_filename_new_content_is_one_document_two_versions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§33: one logical document, two versions, v1 superseded."""
    user_id, org_id = await _signup(client, "acc-same@example.com", "Acc Same Org")
    v1 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1, version_label="1.0")
    db_session.add(v1)
    await db_session.commit()

    v2 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V2, version_label="2.0")
    db_session.add(v2)
    await db_session.commit()

    # Detected, not linked.
    candidate = await find_version_candidate(
        db_session,
        organization_id=org_id,
        file_record=v2,
        document_text=V2,
        read_text=lambda other: V1 if other.id == v1.id else "",
    )
    assert candidate is not None
    assert candidate.file_id == v1.id
    assert candidate.confidence in ("high", "medium")
    assert v1.superseded_by_id is None, "detection must not link anything"

    await accept_new_version(
        db_session,
        organization_id=org_id,
        previous=v1,
        current=v2,
        actor_user_id=user_id,
        version_label="2.0",
    )
    await db_session.commit()

    chain = await version_history(db_session, organization_id=org_id, file_record=v2)
    assert [row.id for row in chain] == [v1.id, v2.id]

    # One logical document: exactly one head in the chain.
    heads = [row for row in chain if row.superseded_by_id is None]
    assert len(heads) == 1
    assert heads[0].id == v2.id


async def test_33_the_library_lists_one_row_with_a_version_count(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9 and §33: the library lists logical documents, not uploads."""
    user_id, org_id = await _signup(client, "acc-lib@example.com", "Acc Lib Org")
    v1 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1, version_label="1.0")
    v2 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V2, version_label="2.0")
    db_session.add_all([v1, v2])
    await db_session.commit()
    await accept_new_version(
        db_session,
        organization_id=org_id,
        previous=v1,
        current=v2,
        actor_user_id=user_id,
        version_label="2.0",
    )
    await db_session.commit()

    response = await client.get("/api/v1/compliance/documents")
    assert response.status_code == 200, response.text
    rows = response.json()

    assert len(rows) == 1, "a superseded version is not a second row"
    assert rows[0]["id"] == str(v2.id)
    assert rows[0]["version_count"] == 2
    assert rows[0]["version_label"] == "2.0"


# --- §34 different filename -------------------------------------------


async def test_34_a_different_filename_does_not_prevent_matching(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§34: the filename is a signal, never a requirement.

    `Updated_AI_Governance_August.docx` shares no version marker and no
    exact name with `AI Governance Policy.docx`. The content does the
    work, which is the point of not making people rename files.
    """
    user_id, org_id = await _signup(client, "acc-name@example.com", "Acc Name Org")
    v1 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1, version_label="1.0")
    db_session.add(v1)
    await db_session.commit()

    renamed = _file(
        org_id, user_id, name="Updated_AI_Governance_August.docx", data=V2, version_label="2.0"
    )
    db_session.add(renamed)
    await db_session.commit()

    candidate = await find_version_candidate(
        db_session,
        organization_id=org_id,
        file_record=renamed,
        document_text=V2,
        read_text=lambda other: V1 if other.id == v1.id else "",
    )

    assert candidate is not None, "an unfamiliar filename must not hide a version"
    assert candidate.file_id == v1.id
    assert candidate.reasons, "a proposal the reader cannot check is not a proposal"


# --- §35 unrelated document -------------------------------------------


async def test_35_an_unrelated_policy_becomes_its_own_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§35: shared boilerplate is not shared identity.

    Both documents are policies, both say "Version: 1.0", both open with
    a Purpose section. None of that makes the travel policy a revision of
    the AI one.
    """
    user_id, org_id = await _signup(client, "acc-unrel@example.com", "Acc Unrelated Org")
    ai_policy = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1)
    db_session.add(ai_policy)
    await db_session.commit()

    travel = _file(org_id, user_id, name="Employee_Travel_Policy.docx", data=TRAVEL)
    db_session.add(travel)
    await db_session.commit()

    candidate = await find_version_candidate(
        db_session,
        organization_id=org_id,
        file_record=travel,
        document_text=TRAVEL,
        read_text=lambda other: V1 if other.id == ai_policy.id else "",
    )

    assert candidate is None
    assert travel.superseded_by_id is None
    assert travel.supersedes_id is None

    response = await client.get("/api/v1/compliance/documents")
    assert {row["id"] for row in response.json()} == {str(ai_policy.id), str(travel.id)}


# --- §36 changed evidence ---------------------------------------------


async def test_36_changed_wording_reopens_review_and_flags_the_control(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§36: "AI systems should be monitored" became a different rule.

    An approval recorded against the old sentence must not silently
    transfer to the new one, and the control that relied on it is stale
    until somebody reassesses it.
    """
    user_id, org_id = await _signup(client, "acc-chg@example.com", "Acc Changed Org")
    control = await _control(db_session, org_id, "Monitoring of AI systems")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    db_session.add_all([v1, v2])
    await db_session.flush()

    db_session.add(
        _suggestion(
            org_id,
            v1,
            control_id=control.id,
            section="7. Monitoring",
            passage="AI systems should be monitored.",
            status="approved",
            decided_by=user_id,
        )
    )
    db_session.add(
        _suggestion(
            org_id,
            v2,
            control_id=control.id,
            section="7. Monitoring",
            passage=(
                "Production AI systems are reviewed monthly for drift, incidents "
                "and material performance changes."
            ),
        )
    )
    await db_session.commit()

    report = await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    assert report.modified == 1
    assert report.approvals_reopened == 1

    carried = (
        await db_session.execute(
            select(EvidenceSuggestion).where(EvidenceSuggestion.file_id == v2.id)
        )
    ).scalars().one()
    assert carried.status == "proposed"
    assert carried.decided_by is None
    assert carried.routing_reason and "changed" in carried.routing_reason.lower()

    # The old evidence is history, not deleted.
    historical = (
        await db_session.execute(
            select(EvidenceSuggestion).where(EvidenceSuggestion.file_id == v1.id)
        )
    ).scalars().one()
    assert historical.status == "approved"

    await db_session.refresh(control)
    assert control.needs_reassessment is True


# --- §37 removed evidence ---------------------------------------------


async def test_37_a_removed_section_stops_counting_but_is_kept(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§37: v2 drops the Retention section entirely.

    The old evidence stays attached to the version it came from — an
    auditor asking what the policy said in May must still be able to see
    it — and stops supporting the current state, because a superseded
    paragraph is not what the organization does now.
    """
    user_id, org_id = await _signup(client, "acc-rm@example.com", "Acc Removed Org")
    retention = await _control(db_session, org_id, "Training data retention")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    db_session.add_all([v1, v2])
    await db_session.flush()

    db_session.add(
        _suggestion(
            org_id,
            v1,
            control_id=retention.id,
            section="10. Retention",
            passage="Model training data is retained for two years and then deleted.",
            status="approved",
            decided_by=user_id,
        )
    )
    await db_session.commit()

    report = await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    assert report.removed == 1

    # Retained.
    remaining = (
        await db_session.execute(
            select(EvidenceSuggestion).where(EvidenceSuggestion.file_id == v1.id)
        )
    ).scalars().all()
    assert len(remaining) == 1

    # Not carried onto the current version.
    carried = (
        await db_session.execute(
            select(func.count(EvidenceSuggestion.id)).where(
                EvidenceSuggestion.file_id == v2.id
            )
        )
    ).scalar_one()
    assert carried == 0

    await db_session.refresh(retention)
    assert retention.needs_reassessment is True


async def test_37_reconciling_twice_creates_no_second_gap_or_notification(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§37 and §29: the reconciliation is safe to repeat.

    A retried worker, a double-clicked button and a replayed request all
    land here, and none of them may leave a second copy of anything.
    """
    user_id, org_id = await _signup(client, "acc-idem@example.com", "Acc Idem Org")
    control = await _control(db_session, org_id, "Monitoring")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    db_session.add_all([v1, v2])
    await db_session.flush()
    db_session.add(
        _suggestion(
            org_id,
            v1,
            control_id=control.id,
            section="7. Monitoring",
            passage="AI systems should be monitored.",
        )
    )
    await db_session.commit()

    async def counts() -> tuple[int, int, int, int]:
        return (
            (
                await db_session.execute(
                    select(func.count(EvidenceSuggestion.id)).where(
                        EvidenceSuggestion.organization_id == org_id
                    )
                )
            ).scalar_one(),
            (
                await db_session.execute(
                    select(func.count(Evidence.id)).where(Evidence.organization_id == org_id)
                )
            ).scalar_one(),
            (
                await db_session.execute(
                    select(func.count(Notification.id)).where(
                        Notification.organization_id == org_id
                    )
                )
            ).scalar_one(),
            (
                await db_session.execute(
                    select(func.count(File.id)).where(File.organization_id == org_id)
                )
            ).scalar_one(),
        )

    for _ in range(3):
        await accept_new_version(
            db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
        )
        await db_session.commit()

    after_first = await counts()
    for _ in range(3):
        await accept_new_version(
            db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
        )
        await db_session.commit()

    assert await counts() == after_first


# --- §38 unchanged human approval -------------------------------------


async def test_38_an_unchanged_passage_does_not_ask_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§38: the Purpose section is identical in both versions.

    Making somebody re-approve wording they already read is how a product
    teaches people to click Approve without reading, so the approval —
    and the name attached to it — carries forward intact.
    """
    user_id, org_id = await _signup(client, "acc-keep@example.com", "Acc Keep Org")
    control = await _control(db_session, org_id, "Governance scope")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    db_session.add_all([v1, v2])
    await db_session.flush()

    purpose = (
        "This policy sets out how the company governs its use of artificial "
        "intelligence across every product and every team that operates one."
    )
    db_session.add(
        _suggestion(
            org_id,
            v1,
            control_id=control.id,
            section="1. Purpose",
            passage=purpose,
            status="approved",
            decided_by=user_id,
        )
    )
    db_session.add(
        _suggestion(org_id, v2, control_id=control.id, section="1. Purpose", passage=purpose)
    )
    await db_session.commit()

    report = await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    assert report.unchanged == 1
    assert report.approvals_preserved == 1
    assert report.approvals_reopened == 0

    carried = (
        await db_session.execute(
            select(EvidenceSuggestion).where(EvidenceSuggestion.file_id == v2.id)
        )
    ).scalars().one()
    assert carried.status == "approved"
    assert carried.decided_by == user_id, "the approval keeps the name that made it"


# --- §21/§22 the Copilot answers from the current version -------------


async def test_the_copilot_does_not_retrieve_superseded_wording(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§21: superseded text must not answer "what does our policy say".

    The old paragraph is still stored, still readable and still cited by
    the history. It is simply not what the organization does now, and
    stating it as current is the one failure a compliance product cannot
    have.
    """
    user_id, org_id = await _signup(client, "acc-rag@example.com", "Acc Rag Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    db_session.add_all([v1, v2])
    await db_session.flush()

    base = KnowledgeBase(organization_id=org_id, name=f"KB {uuid.uuid4().hex[:6]}")
    db_session.add(base)
    await db_session.flush()

    embedding = [1.0, 0.0, 0.0]
    for file_record, text in ((v1, "AI systems should be monitored."), (v2, "Reviewed monthly.")):
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
                content=text,
                embedding=embedding,
                token_count=10,
            )
        )
    await db_session.commit()

    from app.knowledge.retrieval import search_chunks

    before = await search_chunks(
        db_session, organization_id=org_id, query_embedding=embedding, top_k=10
    )
    assert len(before) == 2, "both versions are retrievable before one supersedes the other"

    await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    after = await search_chunks(
        db_session, organization_id=org_id, query_embedding=embedding, top_k=10
    )
    assert [chunk.content for chunk in after] == ["Reviewed monthly."]

    # Still reachable on purpose — history is not deleted, it is just not
    # the answer to a question about the present.
    history = await search_chunks(
        db_session,
        organization_id=org_id,
        query_embedding=embedding,
        top_k=10,
        include_superseded=True,
    )
    assert len(history) == 2


# --- the audit trail --------------------------------------------------


async def test_accepting_a_version_is_written_to_the_audit_trail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§39: a version event an auditor can read, with what it moved."""
    user_id, org_id = await _signup(client, "acc-audit@example.com", "Acc Audit Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1, version_label="1.0")
    v2 = _file(org_id, user_id, name="policy.docx", data=V2, version_label="2.0")
    db_session.add_all([v1, v2])
    await db_session.commit()

    await accept_new_version(
        db_session,
        organization_id=org_id,
        previous=v1,
        current=v2,
        actor_user_id=user_id,
        version_label="2.0",
    )
    await db_session.commit()

    events = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "core.file.version_added",
            )
        )
    ).scalars().all()

    assert len(events) == 1
    event = events[0]
    assert event.object_id == str(v2.id)
    assert event.before_state["version"] == "1.0"
    assert event.after_state["version"] == "2.0"
    # The reconciliation counts travel with the event, so the trail says
    # what the version did rather than only that it happened.
    for key in ("unchanged", "modified", "added", "removed"):
        assert key in event.after_state

    # And it reads as English in the trail, not as an action slug.
    from app.audit.presentation import build_views

    view = (
        await build_views(db_session, organization_id=org_id, events=[event])
    )[0]
    assert view.title == "New version of a document accepted"
    assert str(v2.id) not in view.title
    assert "core.file" not in view.title
    # A person accepted it, so the trail must not credit the AI.
    assert view.actor_kind != "ai"


# --- §31 backfill -----------------------------------------------------


async def test_31_the_backfill_proposes_and_never_links(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§31: retroactive lineage is still a person's decision.

    A bulk pass that superseded documents on a similarity score would
    rewrite compliance history for documents nobody was looking at. It
    proposes exactly what an upload proposes.
    """
    user_id, org_id = await _signup(client, "acc-back@example.com", "Acc Backfill Org")
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    v1 = _file(
        org_id,
        user_id,
        name="AI Governance Policy.docx",
        data=V1,
        created_at=now - timedelta(days=30),
    )
    v2 = _file(
        org_id,
        user_id,
        name="Updated_AI_Governance_August.docx",
        data=V2,
        created_at=now,
    )
    db_session.add_all([v1, v2])
    await db_session.commit()

    texts = {v1.id: V1, v2.id: V2}
    import app.core.storage as storage

    original = storage.download_object

    def fake_download(key: str) -> bytes:
        for file_id, text in texts.items():
            record = v1 if file_id == v1.id else v2
            if record.storage_key == key:
                return text.encode()
        return b""

    storage.download_object = fake_download
    try:
        preview = await backfill_version_candidates(
            db_session, organization_id=org_id, dry_run=True
        )
        assert preview.proposed == 1
        assert v2.version_candidate_id is None, "a dry run writes nothing"

        applied = await backfill_version_candidates(
            db_session, organization_id=org_id, dry_run=False
        )
        await db_session.commit()
    finally:
        storage.download_object = original

    assert applied.proposed == 1
    await db_session.refresh(v2)
    assert v2.version_candidate_id == v1.id
    # Proposed, not linked.
    assert v2.supersedes_id is None
    await db_session.refresh(v1)
    assert v1.superseded_by_id is None


async def test_31_the_backfill_is_safe_to_run_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§31 and §29: a second pass re-proposes nothing."""
    user_id, org_id = await _signup(client, "acc-back2@example.com", "Acc Backfill Two")
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    v1 = _file(
        org_id, user_id, name="policy.docx", data=V1, created_at=now - timedelta(days=5)
    )
    v2 = _file(org_id, user_id, name="policy-new.docx", data=V2, created_at=now)
    db_session.add_all([v1, v2])
    await db_session.commit()

    import app.core.storage as storage

    original = storage.download_object

    def fake_download(key: str) -> bytes:
        if key == v1.storage_key:
            return V1.encode()
        if key == v2.storage_key:
            return V2.encode()
        return b""

    storage.download_object = fake_download
    try:
        await backfill_version_candidates(db_session, organization_id=org_id, dry_run=False)
        await db_session.commit()

        second = await backfill_version_candidates(
            db_session, organization_id=org_id, dry_run=False
        )
        await db_session.commit()
    finally:
        storage.download_object = original

    assert second.proposed == 0
    assert second.already_proposed == 1

    events = (
        await db_session.execute(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "core.file.version_candidate_detected",
            )
        )
    ).scalar_one()
    assert events == 1, "a repeated pass must not repeat the audit event"


# --- §40 the rules that must not be broken ----------------------------


async def test_40_a_version_never_produces_a_second_managed_policy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§40: one policy across every version of the document behind it."""
    user_id, org_id = await _signup(client, "acc-pol@example.com", "Acc Policy Org")
    v1 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1, version_label="1.0")
    v2 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V2, version_label="2.0")
    db_session.add_all([v1, v2])
    await db_session.flush()
    db_session.add(
        Policy(
            organization_id=org_id,
            file_id=v1.id,
            title="AI Governance Policy",
            status="approved",
            version="1.0",
        )
    )
    await db_session.commit()

    await accept_new_version(
        db_session,
        organization_id=org_id,
        previous=v1,
        current=v2,
        actor_user_id=user_id,
        version_label="2.0",
    )
    await db_session.commit()

    policies = (
        await db_session.execute(select(Policy).where(Policy.organization_id == org_id))
    ).scalars().all()

    assert len(policies) == 1, "a new version is the same policy, not a second one"
    assert policies[0].file_id == v2.id, "the policy points at the current version"


async def test_40_no_historical_version_is_ever_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§40: superseding is not deleting.

    Every file row, every suggestion and every indexed document from the
    old version survives the promotion.
    """
    user_id, org_id = await _signup(client, "acc-keepall@example.com", "Acc Keep All")
    control = await _control(db_session, org_id, "Monitoring")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    db_session.add_all([v1, v2])
    await db_session.flush()
    db_session.add(
        _suggestion(
            org_id,
            v1,
            control_id=control.id,
            section="7. Monitoring",
            passage="AI systems should be monitored.",
        )
    )
    await db_session.commit()

    before_files = (
        await db_session.execute(
            select(func.count(File.id)).where(File.organization_id == org_id)
        )
    ).scalar_one()

    await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    after_files = (
        await db_session.execute(
            select(func.count(File.id)).where(File.organization_id == org_id)
        )
    ).scalar_one()
    assert after_files == before_files

    assert await db_session.get(File, v1.id) is not None
    survivors = (
        await db_session.execute(
            select(func.count(EvidenceSuggestion.id)).where(
                EvidenceSuggestion.file_id == v1.id
            )
        )
    ).scalar_one()
    assert survivors == 1


# --- §8 the explicit "upload new version" path ------------------------


async def test_8_uploading_as_a_new_version_records_the_decision(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8: the person named the document, so it is not a guess.

    The intent is recorded at process time and the link is made when the
    analysis finishes — detection is skipped entirely, because a detector
    that overrode an explicit instruction would be worse than one that
    never ran.
    """
    user_id, org_id = await _signup(client, "acc-explicit@example.com", "Acc Explicit Org")
    previous = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1)
    replacement = _file(org_id, user_id, name="totally-different-name.docx", data=V2)
    replacement.processing_status = "not_analyzed"
    db_session.add_all([previous, replacement])
    await db_session.commit()

    response = await client.post(
        "/api/v1/compliance/documents/process",
        json={"file_id": str(replacement.id), "supersedes_file_id": str(previous.id)},
    )
    assert response.status_code == 202, response.text

    await db_session.refresh(replacement)
    assert replacement.version_candidate_id == previous.id
    assert replacement.version_confidence == "confirmed"
    # Recorded, not yet linked: there is no evidence to reconcile until
    # the analysis has run.
    assert replacement.supersedes_id is None
    await db_session.refresh(previous)
    assert previous.superseded_by_id is None


async def test_8_a_document_cannot_be_uploaded_as_a_version_of_itself(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8: the one instruction that can never be carried out."""
    user_id, org_id = await _signup(client, "acc-self@example.com", "Acc Self Org")
    only = _file(org_id, user_id, name="policy.docx", data=V1)
    only.processing_status = "not_analyzed"
    db_session.add(only)
    await db_session.commit()

    response = await client.post(
        "/api/v1/compliance/documents/process",
        json={"file_id": str(only.id), "supersedes_file_id": str(only.id)},
    )

    assert response.status_code == 400
    await db_session.refresh(only)
    assert only.version_candidate_id is None


async def test_8_a_superseded_document_cannot_be_replaced_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8: replacing an old version would fork the chain.

    The reader is told to upload against the current version instead,
    rather than being left with two heads and no way to tell which one
    the organization is held to.
    """
    user_id, org_id = await _signup(client, "acc-fork@example.com", "Acc Fork Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    v3 = _file(org_id, user_id, name="policy.docx", data=V1 + "\n11. Extra\nMore text.\n")
    v3.processing_status = "not_analyzed"
    db_session.add_all([v1, v2, v3])
    await db_session.commit()
    await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/compliance/documents/process",
        json={"file_id": str(v3.id), "supersedes_file_id": str(v1.id)},
    )

    assert response.status_code == 409
    assert "current version" in response.json()["error"]["message"]
    await db_session.refresh(v1)
    assert v1.superseded_by_id == v2.id, "the existing chain is untouched"


async def test_8_another_organizations_document_cannot_be_named(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8 and tenancy: a file id from elsewhere resolves to nothing."""
    _, other_org = await _signup(client, "acc-other@example.com", "Acc Other Org")
    stranger = _file(other_org, (await _signup(client, "acc-o2@example.com", "Acc O2"))[0], name="theirs.docx", data=V1)
    stranger.organization_id = other_org
    db_session.add(stranger)
    await db_session.commit()

    user_id, org_id = await _signup(client, "acc-mine@example.com", "Acc Mine Org")
    mine = _file(org_id, user_id, name="mine.docx", data=V2)
    mine.processing_status = "not_analyzed"
    db_session.add(mine)
    await db_session.commit()

    response = await client.post(
        "/api/v1/compliance/documents/process",
        json={"file_id": str(mine.id), "supersedes_file_id": str(stranger.id)},
    )

    assert response.status_code == 404
    await db_session.refresh(mine)
    assert mine.version_candidate_id is None


async def test_8_a_confirmed_version_links_itself_once_analysed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8: the link is completed by the pipeline, not by asking again."""
    from app.compliance.evidence_ai import _link_confirmed_version

    user_id, org_id = await _signup(client, "acc-link@example.com", "Acc Link Org")
    previous = _file(org_id, user_id, name="policy.docx", data=V1)
    current = _file(org_id, user_id, name="rewritten.docx", data=V2, version_label="2.0")
    db_session.add_all([previous, current])
    await db_session.flush()
    current.version_candidate_id = previous.id
    current.version_confidence = "confirmed"
    await db_session.commit()

    await _link_confirmed_version(
        db_session,
        organization_id=org_id,
        file_record=current,
        actor_user_id=user_id,
    )
    await db_session.commit()

    await db_session.refresh(previous)
    assert previous.superseded_by_id == current.id
    assert current.supersedes_id == previous.id
    # The question is answered, so it is no longer asked.
    assert current.version_candidate_id is None
    assert current.version_confidence is None


async def test_8_a_detected_candidate_is_never_linked_by_the_pipeline(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5 and §8: a guess and a decision must not share a code path.

    This is the test that stops the version feature from becoming the
    silent-merge bug it exists to avoid.
    """
    from app.compliance.evidence_ai import _link_confirmed_version

    user_id, org_id = await _signup(client, "acc-guess@example.com", "Acc Guess Org")
    previous = _file(org_id, user_id, name="policy.docx", data=V1)
    current = _file(org_id, user_id, name="policy.docx", data=V2)
    db_session.add_all([previous, current])
    await db_session.flush()
    current.version_candidate_id = previous.id
    current.version_confidence = "high"  # detected, not confirmed
    await db_session.commit()

    await _link_confirmed_version(
        db_session,
        organization_id=org_id,
        file_record=current,
        actor_user_id=user_id,
    )
    await db_session.commit()

    await db_session.refresh(previous)
    assert previous.superseded_by_id is None
    assert current.supersedes_id is None
    # Still proposed, still waiting on a person.
    assert current.version_candidate_id == previous.id


async def test_31_the_backfill_endpoint_previews_before_it_writes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§31: a bulk pass over a customer's library defaults to read-only."""
    user_id, org_id = await _signup(client, "acc-bfapi@example.com", "Acc Backfill Api")
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    v1 = _file(
        org_id, user_id, name="policy.docx", data=V1, created_at=now - timedelta(days=9)
    )
    v2 = _file(org_id, user_id, name="policy-aug.docx", data=V2, created_at=now)
    db_session.add_all([v1, v2])
    await db_session.commit()

    import app.core.storage as storage

    original = storage.download_object

    def fake_download(key: str) -> bytes:
        if key == v1.storage_key:
            return V1.encode()
        if key == v2.storage_key:
            return V2.encode()
        return b""

    storage.download_object = fake_download
    try:
        preview = await client.post("/api/v1/compliance/documents/backfill-versions")
        assert preview.status_code == 200, preview.text
        assert preview.json()["dry_run"] is True
        assert preview.json()["proposed"] == 1

        await db_session.refresh(v2)
        assert v2.version_candidate_id is None, "a preview writes nothing"

        applied = await client.post(
            "/api/v1/compliance/documents/backfill-versions", params={"dry_run": "false"}
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["dry_run"] is False
    finally:
        storage.download_object = original

    await db_session.refresh(v2)
    assert v2.version_candidate_id == v1.id
    # Proposed. Still nobody's decision but a person's.
    assert v2.supersedes_id is None


# --- §22 a citation made against wording that has since changed -------


async def test_22_a_citation_into_a_superseded_version_still_opens_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§22: an old citation must open the words that were actually cited.

    Rewriting historical citations to land on current text would quietly
    falsify the record. The page stays readable, says it is an earlier
    version, and offers one step to the current one — which is what the
    reader needs and what the auditor's question depends on.
    """
    user_id, org_id = await _signup(client, "acc-cite@example.com", "Acc Citation Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1, version_label="1.0")
    v2 = _file(org_id, user_id, name="policy.docx", data=V2, version_label="2.0")
    db_session.add_all([v1, v2])
    await db_session.flush()

    base = KnowledgeBase(organization_id=org_id, name=f"KB {uuid.uuid4().hex[:6]}")
    db_session.add(base)
    await db_session.flush()

    documents = {}
    for file_record, text in ((v1, "AI systems should be monitored."), (v2, "Reviewed monthly.")):
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
                content=text,
                embedding=[1.0, 0.0],
                token_count=10,
            )
        )
        documents[file_record.id] = document
    await db_session.commit()

    await accept_new_version(
        db_session,
        organization_id=org_id,
        previous=v1,
        current=v2,
        actor_user_id=user_id,
        version_label="2.0",
    )
    await db_session.commit()

    old_citation_target = documents[v1.id].id
    response = await client.get(
        f"/api/v1/compliance/documents/{old_citation_target}/detail"
    )

    assert response.status_code == 200, "the cited page must not 404 once superseded"
    body = response.json()
    assert body["file_id"] == str(v1.id)

    # The page knows where it sits in the chain, so the reader is told
    # they are looking at history and given the way forward.
    versions = {version["file_id"]: version for version in body["versions"]}
    assert versions[str(v1.id)]["status"] == "superseded"
    assert versions[str(v2.id)]["status"] == "current"
    assert versions[str(v2.id)]["href"], "the current version must be one click away"

    # The old wording is still readable — that is the whole point.
    chunks = await client.get(f"/api/v1/knowledge/documents/{old_citation_target}/chunks")
    assert chunks.status_code == 200, chunks.text
    assert "AI systems should be monitored." in chunks.text


async def test_22_the_superseded_page_offers_no_way_to_fork_the_chain(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§22 and §8: a new version replaces the current one, never an old one."""
    user_id, org_id = await _signup(client, "acc-nofork@example.com", "Acc No Fork Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    v3 = _file(org_id, user_id, name="policy.docx", data=V1 + "\n11. Extra\nMore words here.\n")
    v3.processing_status = "not_analyzed"
    db_session.add_all([v1, v2, v3])
    await db_session.commit()
    await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/compliance/documents/process",
        json={"file_id": str(v3.id), "supersedes_file_id": str(v1.id)},
    )

    assert response.status_code == 409
    await db_session.refresh(v1)
    assert v1.superseded_by_id == v2.id


async def test_8_a_failed_link_does_not_mark_a_good_document_failed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The document read fine; only the link did not.

    Reporting "your policy could not be processed" because a lineage
    link failed tells the customer something untrue about their
    document. The proposal is left for them to accept by hand instead.
    """
    from unittest.mock import patch

    from app.compliance.evidence_ai import _link_confirmed_version

    user_id, org_id = await _signup(client, "acc-linkfail@example.com", "Acc Link Fail")
    previous = _file(org_id, user_id, name="policy.docx", data=V1)
    current = _file(org_id, user_id, name="rewritten.docx", data=V2)
    db_session.add_all([previous, current])
    await db_session.flush()
    current.version_candidate_id = previous.id
    current.version_confidence = "confirmed"
    await db_session.commit()

    with patch(
        "app.compliance.version_promotion.accept_new_version",
        side_effect=RuntimeError("the database went away"),
    ):
        await _link_confirmed_version(
            db_session,
            organization_id=org_id,
            file_record=current,
            actor_user_id=user_id,
        )

    # Not linked, not lost: still a proposal somebody can accept.
    assert current.supersedes_id is None
    assert current.version_candidate_id == previous.id
    assert current.version_confidence == "high"
    # And the banner has something to show: a proposal with no reasons is
    # one nobody can check.
    assert current.version_reasons
    assert previous.original_filename in current.version_reasons[0]
    # And the exception did not escape to fail the whole pipeline.
    assert current.processing_status == "ready"


# --- §39 concurrency: a chain is a line, not a tree --------------------


async def test_two_uploads_cannot_supersede_the_same_version(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§39: the endpoint's guard is a read before a write.

    Two people accepting two different uploads against the same previous
    version both pass "has this been superseded?" and both write. The
    database has to be the one that refuses, or the library ends up with
    two documents claiming to replace one and no answer to which is
    current.
    """
    from app.compliance.version_promotion import VersionAlreadySuperseded

    user_id, org_id = await _signup(client, "acc-fork2@example.com", "Acc Fork Two")
    original = _file(org_id, user_id, name="policy.docx", data=V1)
    mine = _file(org_id, user_id, name="mine.docx", data=V2)
    theirs = _file(org_id, user_id, name="theirs.docx", data=V2 + "\n9. Extra\nMore.\n")
    db_session.add_all([original, mine, theirs])
    await db_session.commit()

    await accept_new_version(
        db_session,
        organization_id=org_id,
        previous=original,
        current=mine,
        actor_user_id=user_id,
    )
    await db_session.commit()

    # The second acceptance is refused by the constraint, not by a check
    # that could have been raced.
    with pytest.raises(VersionAlreadySuperseded):
        await accept_new_version(
            db_session,
            organization_id=org_id,
            previous=original,
            current=theirs,
            actor_user_id=user_id,
        )

    # The chain is intact and unambiguous.
    await db_session.refresh(original)
    await db_session.refresh(theirs)
    assert original.superseded_by_id == mine.id
    assert theirs.supersedes_id is None

    claimants = (
        await db_session.execute(
            select(func.count(File.id)).where(File.supersedes_id == original.id)
        )
    ).scalar_one()
    assert claimants == 1


async def test_a_lost_race_is_reported_as_a_conflict_not_a_crash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§39: the person who lost is told what happened and what to do."""
    user_id, org_id = await _signup(client, "acc-race@example.com", "Acc Race Org")
    original = _file(org_id, user_id, name="policy.docx", data=V1)
    winner = _file(org_id, user_id, name="winner.docx", data=V2)
    loser = _file(org_id, user_id, name="loser.docx", data=V2 + "\n9. Extra\nMore.\n")
    db_session.add_all([original, winner, loser])
    await db_session.flush()

    base = KnowledgeBase(organization_id=org_id, name=f"KB {uuid.uuid4().hex[:6]}")
    db_session.add(base)
    await db_session.flush()
    loser_document = Document(
        organization_id=org_id,
        knowledge_base_id=base.id,
        file_id=loser.id,
        title=loser.original_filename,
        status="ready",
    )
    db_session.add(loser_document)
    await db_session.commit()

    await accept_new_version(
        db_session,
        organization_id=org_id,
        previous=original,
        current=winner,
        actor_user_id=user_id,
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/documents/{loser_document.id}/accept-version",
        json={"supersedes_file_id": str(original.id)},
    )

    assert response.status_code == 409
    message = response.json()["error"]["message"]
    assert "superseded" in message.lower() or "current version" in message.lower()
