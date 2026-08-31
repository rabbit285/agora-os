"""Upload a policy once.

The reported confusion: ten analysed policy documents on one screen, and
"No managed policies yet" on another. The product had read
`03_AI_Governance_Policy.docx`, classified it, extracted ten pieces of
evidence and mapped them to ten controls — then asked the customer to go
elsewhere, press "Add policy", and type "AI Governance Policy" into a box.

So classification creates the governance record. What it must never do is
fill it in: a detected policy has no owner, no approval and no review
date, because the product cannot know those and a plausible default would
be a fabricated compliance record. That line — detection is not approval —
is what most of these tests are about.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Policy, PolicyVersion
from app.compliance.policy_governance import (
    backfill_organization,
    days_until_review,
    detect_version,
    ensure_policy_for_document,
    looks_like_a_policy,
    missing_governance,
    promote_document_to_current_version,
    review_state,
)
from app.core.models import File, Membership
from app.seed import _ensure_compliance_catalog

POLICY_TEXT = """ACME AI SAAS - AI GOVERNANCE POLICY
Version 2.1

Section 7 Monitoring
Product teams must monitor material failures, user feedback and incidents.
"""


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


async def _signup(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"policy-{uuid.uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery",
            "full_name": "Acme Compliance Lead",
            "organization_name": f"Acme Policy {uuid.uuid4().hex[:6]}",
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


async def _classified_file(
    client: AsyncClient,
    db: AsyncSession,
    *,
    filename: str,
    document_type: str | None,
    domain: str = "AI Governance",
) -> File:
    """A file in the state the analysis pipeline leaves it in."""
    response = await client.post(
        "/api/v1/files/upload-url",
        json={
            "filename": filename,
            "content_type": "text/plain",
            "size_bytes": len(POLICY_TEXT),
            "classification": "confidential",
        },
    )
    assert response.status_code == 200, response.text
    record = await db.get(File, uuid.UUID(response.json()["file_id"]))
    assert record is not None
    record.processing_status = "ready"
    record.document_type = document_type
    record.document_domain = domain
    await db.commit()
    return record


# --- Detection ---------------------------------------------------------


def test_detection_reads_the_classification_not_the_filename() -> None:
    """A file called `final_v3.docx` containing an access control policy
    has to be caught; `policy_template.docx` containing a template must
    not be."""
    for document_type in (
        "AI Policy",
        "Information Security Policy",
        "Data Retention Policy",
        "Incident Response Procedure",
        "Special-Category Personal Data Processing Policy",
    ):
        assert looks_like_a_policy(document_type), document_type

    for document_type in (
        "Privacy Notice",
        "Record of Processing Activities",
        "Data Processing Addendum",
        "Vendor Privacy and Security Assessment",
        "Training materials and completion records",
        "Policy template",
        None,
    ):
        assert not looks_like_a_policy(document_type), document_type


def test_a_version_is_recorded_only_when_the_document_states_one() -> None:
    """A default of "1.0" would put a version the customer never wrote
    into a record an auditor may read."""
    assert detect_version("AI POLICY\nVersion 2.1\n") == "2.1"
    assert detect_version("AI POLICY\nv3\n") == "3"
    assert detect_version("AI POLICY\nno version anywhere") is None
    assert detect_version(None) is None


async def test_a_policy_document_gets_a_governance_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    file_record = await _classified_file(
        client,
        db_session,
        filename="03_AI_Governance_Policy.txt",
        document_type="AI Governance Policy",
    )

    policy = await ensure_policy_for_document(
        db_session,
        organization_id=organization_id,
        file_record=file_record,
        document_text=POLICY_TEXT,
    )
    await db_session.commit()

    assert policy is not None
    assert policy.title == "AI Governance Policy"
    assert policy.file_id == file_record.id
    assert policy.detected_automatically is True
    # Detected, not approved.
    assert policy.status == "needs_review"
    assert policy.owner_id is None
    assert policy.approved_by is None
    assert policy.approved_at is None
    assert policy.next_review_at is None
    # The version was in the document, so it is recorded.
    assert policy.version == "2.1"


async def test_detection_never_approves(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The line this feature turns on. Automatic creation must never
    produce an approval — that is an organizational act, and a product
    that performs it is forging a record."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    file_record = await _classified_file(
        client, db_session, filename="policy.txt", document_type="Access Control Policy"
    )

    policy = await ensure_policy_for_document(
        db_session, organization_id=organization_id, file_record=file_record
    )
    await db_session.commit()
    assert policy is not None
    assert policy.status != "approved"
    assert set(missing_governance(policy)) == {
        "Owner",
        "Version",
        "Approval",
        "Next review date",
    }


async def test_a_non_policy_document_gets_no_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Most uploads are not policies. A governance record for a training
    register would be noise in the one list that has to stay short."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    file_record = await _classified_file(
        client,
        db_session,
        filename="05_Record_of_Processing_Activities.txt",
        document_type="Record of Processing Activities",
    )

    policy = await ensure_policy_for_document(
        db_session, organization_id=organization_id, file_record=file_record
    )
    assert policy is None


# --- Duplicate prevention ---------------------------------------------


async def test_reprocessing_a_document_does_not_create_a_second_policy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The backfill runs whenever the list is opened, and documents get
    reanalysed. Either would multiply records without this."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    file_record = await _classified_file(
        client, db_session, filename="policy.txt", document_type="AI Governance Policy"
    )

    first = await ensure_policy_for_document(
        db_session, organization_id=organization_id, file_record=file_record
    )
    await db_session.commit()
    second = await ensure_policy_for_document(
        db_session, organization_id=organization_id, file_record=file_record
    )
    await db_session.commit()

    assert first is not None and second is not None
    assert first.id == second.id
    count = len(
        (
            await db_session.execute(
                select(Policy).where(Policy.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    assert count == 1


async def test_a_second_document_for_the_same_policy_is_not_a_second_policy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Uploading `AI_Governance_Policy_v2.docx` is a new version of an
    existing policy, not an unrelated one."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)

    first_file = await _classified_file(
        client, db_session, filename="v1.txt", document_type="AI Governance Policy"
    )
    original = await ensure_policy_for_document(
        db_session, organization_id=organization_id, file_record=first_file
    )
    await db_session.commit()

    second_file = await _classified_file(
        client, db_session, filename="v2.txt", document_type="AI Governance Policy"
    )
    linked = await ensure_policy_for_document(
        db_session, organization_id=organization_id, file_record=second_file
    )
    await db_session.commit()

    assert original is not None and linked is not None
    assert linked.id == original.id
    # And it did not silently swap the document under an approved policy.
    assert linked.file_id == first_file.id


# --- Versioning --------------------------------------------------------


async def test_a_new_version_keeps_the_old_document(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """"What did your retention policy say in March" is a question an
    auditor asks. A product that overwrote the file cannot answer it."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)

    old_file = await _classified_file(
        client, db_session, filename="v1.txt", document_type="Data Retention Policy"
    )
    policy = await ensure_policy_for_document(
        db_session, organization_id=organization_id, file_record=old_file
    )
    await db_session.commit()
    assert policy is not None

    # Approved, so we can check the approval does not carry over.
    policy.status = "approved"
    policy.approved_at = datetime.now(UTC)
    await db_session.commit()

    new_file = await _classified_file(
        client, db_session, filename="v2.txt", document_type="Data Retention Policy"
    )
    await promote_document_to_current_version(
        db_session,
        organization_id=organization_id,
        policy=policy,
        file_record=new_file,
        actor_user_id=None,
        version="2.0",
    )
    await db_session.commit()

    assert policy.file_id == new_file.id
    assert policy.version == "2.0"
    # A new document is a new thing to sign off.
    assert policy.status == "needs_review"
    assert policy.approved_at is None

    versions = list(
        (
            await db_session.execute(
                select(PolicyVersion).where(PolicyVersion.policy_id == policy.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(versions) == 2
    by_file = {v.file_id: v for v in versions}
    assert by_file[old_file.id].status == "superseded"
    assert by_file[old_file.id].superseded_at is not None
    assert by_file[new_file.id].status == "current"


# --- Review cycles -----------------------------------------------------


def test_review_state_is_derived_from_the_calendar() -> None:
    now = datetime(2026, 8, 24, tzinfo=UTC)

    def policy_with(**kwargs: object) -> Policy:
        return Policy(organization_id=uuid.uuid4(), title="P", status="approved", **kwargs)

    assert review_state(policy_with(), now=now) == "not_scheduled"
    assert (
        review_state(policy_with(next_review_at=now + timedelta(days=200)), now=now)
        == "scheduled"
    )
    assert (
        review_state(policy_with(next_review_at=now + timedelta(days=10)), now=now)
        == "due_soon"
    )
    assert (
        review_state(policy_with(next_review_at=now - timedelta(days=1)), now=now)
        == "overdue"
    )
    # A retired policy has no review obligation.
    retired = policy_with(next_review_at=now - timedelta(days=400))
    retired.status = "retired"
    assert review_state(retired, now=now) == "not_applicable"


def test_days_until_review_is_computed_on_the_server() -> None:
    """A `Date.now()` inside a React render is impure and gives a
    different answer every paint, so the number comes from here."""
    now = datetime(2026, 8, 24, tzinfo=UTC)
    policy = Policy(
        organization_id=uuid.uuid4(),
        title="P",
        status="approved",
        next_review_at=now + timedelta(days=30),
    )
    assert days_until_review(policy, now=now) == 30
    policy.next_review_at = now - timedelta(days=5)
    assert days_until_review(policy, now=now) == -5
    policy.next_review_at = None
    assert days_until_review(policy, now=now) is None


# --- Backfill ----------------------------------------------------------


async def test_the_backfill_governs_documents_uploaded_before_detection(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Detection was added after customers had libraries of policies.
    Without this, an existing tenant sees "no policies" beside ten policy
    documents — the exact confusion this feature removes."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)

    for filename, document_type in (
        ("02_Information_Security_Policy.txt", "policy"),
        ("03_AI_Governance_Policy.txt", "AI Policy"),
        ("06_Data_Retention_Policy.txt", "Data Retention Policy"),
        ("01_Privacy_Notice.txt", "Privacy Notice"),
        ("05_RoPA.txt", "Record of Processing Activities"),
    ):
        await _classified_file(
            client, db_session, filename=filename, document_type=document_type
        )

    counts = await backfill_organization(db_session, organization_id=organization_id)
    assert counts["created"] == 3, counts
    assert counts["skipped"] == 2, counts

    titles = sorted(
        policy.title
        for policy in (
            await db_session.execute(
                select(Policy).where(Policy.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    # The classifier returned a bare "policy" for one document, which is a
    # category not a name — the filename is genuinely more informative.
    assert titles == [
        "AI Policy",
        "Data Retention Policy",
        "Information Security Policy",
    ]

    # Idempotent.
    again = await backfill_organization(db_session, organization_id=organization_id)
    assert again["created"] == 0


# --- Through the API ---------------------------------------------------


async def test_the_acceptance_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    """Upload, then assign an owner, approve, and schedule a review —
    without ever pressing "Add policy"."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    file_record = await _classified_file(
        client,
        db_session,
        filename="03_AI_Governance_Policy.txt",
        document_type="AI Governance Policy",
    )
    await ensure_policy_for_document(
        db_session,
        organization_id=organization_id,
        file_record=file_record,
        document_text=POLICY_TEXT,
    )
    await db_session.commit()

    listed = (await client.get("/api/v1/compliance/policies")).json()
    assert len(listed) == 1
    row = listed[0]
    assert row["title"] == "AI Governance Policy"
    assert row["status"] == "needs_review"
    assert row["detected_automatically"] is True
    assert row["document_filename"] == "03_AI_Governance_Policy.txt"
    assert "Owner" in row["missing_governance"]

    policy_id = row["id"]
    me = (await client.get("/api/v1/auth/me")).json()

    governed = await client.patch(
        f"/api/v1/compliance/policies/{policy_id}/governance",
        json={
            "owner_id": me["id"],
            "next_review_at": (datetime.now(UTC) + timedelta(days=365)).isoformat(),
            "review_frequency_months": 12,
        },
    )
    assert governed.status_code == 200, governed.text
    assert governed.json()["owner_id"] == me["id"]
    assert "Owner" not in governed.json()["missing_governance"]

    approved = await client.post(
        f"/api/v1/compliance/policies/{policy_id}/approve", json={"note": "Signed off"}
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == me["id"]
    assert body["approved_at"]
    assert body["missing_governance"] == []

    # The approval is in the audit trail, attributed to a person.
    events = (await client.get(f"/api/v1/audit-events?object_id={policy_id}")).json()
    actions = {event["action"] for event in events}
    assert "compliance.policy.detected" in actions
    assert "compliance.policy.approved" in actions
    approval = next(e for e in events if e["action"] == "compliance.policy.approved")
    assert approval["actor_user_id"] == me["id"]
    assert approval["label"] == "Approved"


async def test_the_detail_page_reads_relationships_it_does_not_duplicate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Controls come from the evidence the document already produced, not
    a second mapping the customer maintains by hand."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    file_record = await _classified_file(
        client, db_session, filename="policy.txt", document_type="AI Governance Policy"
    )
    policy = await ensure_policy_for_document(
        db_session, organization_id=organization_id, file_record=file_record
    )
    await db_session.commit()
    assert policy is not None

    detail = (await client.get(f"/api/v1/compliance/policies/{policy.id}")).json()
    assert detail["title"] == "AI Governance Policy"
    assert detail["versions"], "the current version has to be in the history"
    assert detail["versions"][0]["status"] == "current"
    # No evidence has been attached in this test, so no controls — the
    # point is that the field is read, not invented.
    assert detail["controls"] == []


async def test_a_document_row_links_to_its_policy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The customer never has to make this connection by hand."""
    await _signup(client)
    organization_id = await _organization_id(client, db_session)
    file_record = await _classified_file(
        client, db_session, filename="policy.txt", document_type="AI Governance Policy"
    )
    policy = await ensure_policy_for_document(
        db_session, organization_id=organization_id, file_record=file_record
    )
    await db_session.commit()
    assert policy is not None

    documents = (await client.get("/api/v1/compliance/documents")).json()
    entry = next(d for d in documents if d["id"] == str(file_record.id))
    assert entry["policy_id"] == str(policy.id)
    assert entry["policy_title"] == "AI Governance Policy"
    assert entry["policy_status"] == "needs_review"
