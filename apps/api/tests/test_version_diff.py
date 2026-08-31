"""§12 and §25: what changed between two versions.

"Version 2 is current" does not answer the question a reviewer is
asking. They need to know which section moved, because that is what
decides whether the control that relied on it still holds.

The unit is the section, not the line. A policy re-flowed by a word
processor changes every line and says nothing new; these tests pin that
distinction, because a diff that cries wolf on formatting is a diff
nobody reads.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.version_diff import (
    MIN_SECTION_CHARS,
    REWRITTEN_BELOW,
    VersionDiff,
    diff_text,
    split_sections,
)
from app.compliance.version_promotion import accept_new_version
from app.core.dedupe import content_fingerprint
from app.core.models import File
from app.knowledge.models import Document, DocumentChunk, KnowledgeBase

V1 = """AI Governance Policy

1. Purpose
This policy sets out how the company governs its use of artificial intelligence.

7. Monitoring
AI systems should be monitored.

10. Retention
Model training data is retained for two years and then deleted.
"""

V2 = """AI Governance Policy

1. Purpose
This policy sets out how the company governs its use of artificial intelligence.

7. Monitoring
Production AI systems are reviewed monthly for drift, incidents and material
performance changes by the AI Governance Lead.

8. Human oversight
Every production AI system has a named human owner who can halt it.
"""


def _changes_by_section(previous: str, current: str) -> dict[str | None, str]:
    return {change.section: change.change for change in diff_text(previous, current)}


# --- splitting --------------------------------------------------------


def test_a_document_is_divided_by_its_own_headings() -> None:
    sections = split_sections(V1)

    assert "1. Purpose" in sections
    assert "7. Monitoring" in sections
    assert "10. Retention" in sections
    assert sections["7. Monitoring"] == "AI systems should be monitored."


def test_the_heading_names_the_section_and_is_not_part_of_it() -> None:
    """So a renamed heading reads as a new section, not a reworded one."""
    sections = split_sections(V1)

    assert "7. Monitoring" not in sections["7. Monitoring"]


def test_reflowing_a_paragraph_is_not_a_change() -> None:
    """The failure this whole module exists to avoid.

    A word processor rewrapping every line must not report the document
    as rewritten, or the diff becomes something people click past.
    """
    reflowed = V1.replace(
        "This policy sets out how the company governs its use of artificial intelligence.",
        "This policy sets out how the company\ngoverns its use of artificial\nintelligence.",
    )

    assert _changes_by_section(V1, reflowed)["1. Purpose"] == "unchanged"


# --- comparing --------------------------------------------------------


def test_a_rewritten_section_is_reported_as_rewritten() -> None:
    assert _changes_by_section(V1, V2)["7. Monitoring"] == "rewritten"


def test_a_new_section_is_reported_as_added() -> None:
    assert _changes_by_section(V1, V2)["8. Human oversight"] == "added"


def test_a_dropped_section_is_reported_as_removed() -> None:
    assert _changes_by_section(V1, V2)["10. Retention"] == "removed"


def test_an_untouched_section_is_reported_as_unchanged() -> None:
    assert _changes_by_section(V1, V2)["1. Purpose"] == "unchanged"


def test_inserting_a_section_does_not_disturb_the_ones_after_it() -> None:
    """Sections line up on what they *are*, not on where they fall."""
    with_insert = V1.replace(
        "7. Monitoring",
        "5. Scope\nThis policy applies to every product and team.\n\n7. Monitoring",
    )
    changes = _changes_by_section(V1, with_insert)

    assert changes["5. Scope"] == "added"
    assert changes["7. Monitoring"] == "unchanged"
    assert changes["10. Retention"] == "unchanged"


def test_a_light_edit_is_reported_as_an_edit_not_a_rewrite() -> None:
    """The difference a reviewer's time depends on."""
    edited = V1.replace(
        "AI systems should be monitored.",
        "AI systems should be monitored continuously.",
    )

    assert _changes_by_section(V1, edited)["7. Monitoring"] == "reworded"


def test_a_stray_short_line_is_not_reported_as_a_change() -> None:
    """Page numbers and footers are not sections anybody approved."""
    noisy = V2 + "\n99. x\nPage 2\n"
    sections = [
        change.section
        for change in diff_text(V1, noisy)
        if change.change == "added"
    ]

    assert "99. x" not in sections
    assert len("Page 2") < MIN_SECTION_CHARS


def test_comparing_a_document_with_itself_finds_nothing_changed() -> None:
    changes = diff_text(V1, V1)

    assert changes
    assert all(change.change == "unchanged" for change in changes)


def test_the_rewrite_threshold_is_a_similarity_not_a_guess() -> None:
    """Documented so the number can be argued with rather than tuned blind."""
    assert 0.5 < REWRITTEN_BELOW < 1.0


# --- what the reader is told ------------------------------------------


def test_the_headline_says_what_happened_in_one_sentence() -> None:
    diff = VersionDiff(
        previous_file_id=uuid.uuid4(),
        current_file_id=uuid.uuid4(),
        changes=diff_text(V1, V2),
    )

    assert diff.modified == 1
    assert diff.added == 1
    assert diff.removed == 1
    assert diff.headline == "1 section changed, 1 added, 1 removed."


def test_an_identical_pair_says_so_plainly() -> None:
    diff = VersionDiff(
        previous_file_id=uuid.uuid4(),
        current_file_id=uuid.uuid4(),
        changes=diff_text(V1, V1),
    )

    assert "did not change" in diff.headline


def test_every_change_explains_itself_without_jargon() -> None:
    for change in diff_text(V1, V2):
        assert change.summary.endswith("."), "a sentence, not a label"
        # The section is named, so the reader knows what is being talked
        # about without cross-referencing anything.
        assert (change.section or "opening") in change.summary
        # No snake_case, no identifiers, no similarity score.
        assert "_" not in change.summary
        assert str(change.similarity) not in change.summary


# --- through the API --------------------------------------------------


async def _signup(client: AsyncClient, email: str, org: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Diff Tester",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


async def _indexed(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    name: str,
    text: str,
    label: str,
) -> tuple[File, Document]:
    file_record = File(
        organization_id=org_id,
        storage_key=f"org/{org_id}/{uuid.uuid4()}/{name}",
        original_filename=name,
        content_type="text/plain",
        size_bytes=len(text),
        uploaded_by=user_id,
        processing_status="ready",
        content_hash=content_fingerprint(text.encode()),
        version_label=label,
    )
    db.add(file_record)
    await db.flush()

    base = (
        await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.organization_id == org_id)
        )
    ).scalars().first()
    if base is None:
        base = KnowledgeBase(organization_id=org_id, name="Docs")
        db.add(base)
        await db.flush()

    document = Document(
        organization_id=org_id,
        knowledge_base_id=base.id,
        file_id=file_record.id,
        title=name,
        status="ready",
    )
    db.add(document)
    await db.flush()
    db.add(
        DocumentChunk(
            organization_id=org_id,
            document_id=document.id,
            chunk_index=0,
            content=text,
            embedding=[0.1, 0.2],
            token_count=10,
        )
    )
    await db.flush()
    return file_record, document


async def test_the_api_compares_two_versions_of_one_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "diff-api@example.com", "Diff Api Org")
    v1, _ = await _indexed(db_session, org_id, user_id, name="policy.docx", text=V1, label="1.0")
    v2, doc2 = await _indexed(
        db_session, org_id, user_id, name="policy.docx", text=V2, label="2.0"
    )
    await db_session.commit()
    await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/compliance/documents/{doc2.id}/compare", params={"against": str(v1.id)}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["previous_label"] == "1.0"
    assert body["current_label"] == "2.0"
    assert body["added"] == 1
    assert body["removed"] == 1
    assert body["modified"] == 1
    sections = {change["section"]: change["change"] for change in body["changes"]}
    assert sections["7. Monitoring"] == "rewritten"
    assert sections["8. Human oversight"] == "added"
    assert sections["10. Retention"] == "removed"


async def test_the_api_orders_the_comparison_oldest_first_either_way(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """So "added" and "removed" always mean what the reader expects.

    Asking from the old version's page must not invert the report.
    """
    user_id, org_id = await _signup(client, "diff-order@example.com", "Diff Order Org")
    v1, doc1 = await _indexed(
        db_session, org_id, user_id, name="policy.docx", text=V1, label="1.0"
    )
    v2, _ = await _indexed(db_session, org_id, user_id, name="policy.docx", text=V2, label="2.0")
    await db_session.commit()
    await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/compliance/documents/{doc1.id}/compare", params={"against": str(v2.id)}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["previous_label"] == "1.0"
    assert body["current_label"] == "2.0"
    assert body["added"] == 1, "8. Human oversight is added by v2, whichever page asked"


async def test_a_document_cannot_be_compared_with_an_unrelated_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The comparison is scoped to one document's own chain.

    Diffing two unrelated policies is not a feature; it is a way to read
    a document you did not open.
    """
    user_id, org_id = await _signup(client, "diff-scope@example.com", "Diff Scope Org")
    _, doc = await _indexed(db_session, org_id, user_id, name="a.docx", text=V1, label="1.0")
    other, _ = await _indexed(db_session, org_id, user_id, name="b.docx", text=V2, label="1.0")
    await db_session.commit()

    response = await client.get(
        f"/api/v1/compliance/documents/{doc.id}/compare", params={"against": str(other.id)}
    )

    assert response.status_code == 404


async def test_a_version_cannot_be_compared_with_itself(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "diff-self@example.com", "Diff Self Org")
    only, doc = await _indexed(
        db_session, org_id, user_id, name="policy.docx", text=V1, label="1.0"
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/compliance/documents/{doc.id}/compare", params={"against": str(only.id)}
    )

    assert response.status_code == 400


async def test_the_comparison_never_leaks_another_organizations_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    stranger_id, other_org = await _signup(client, "diff-them@example.com", "Diff Them Org")
    theirs, _ = await _indexed(
        db_session, other_org, stranger_id, name="theirs.docx", text=V2, label="1.0"
    )
    await db_session.commit()

    user_id, org_id = await _signup(client, "diff-me@example.com", "Diff Me Org")
    _, mine = await _indexed(
        db_session, org_id, user_id, name="mine.docx", text=V1, label="1.0"
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/compliance/documents/{mine.id}/compare", params={"against": str(theirs.id)}
    )

    assert response.status_code == 404
