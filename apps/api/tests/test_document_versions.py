"""Nobody should have to name a file `AI_Governance_Policy_v2.docx`.

Three outcomes, and the difference between them is the whole feature:
the same bytes are a duplicate, different bytes that are confidently the
same document are a new version, and everything else is a new document.

The middle case is a judgement, so these tests pin the judgement: what
counts as evidence for it, what is not enough on its own, and — most
importantly — what happens to the human decisions that were made against
the version being replaced.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.document_versioning import (
    CONTENT_FLOOR,
    HIGH_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    content_similarity,
    detect_effective_date,
    detect_version_label,
    heading_similarity,
    score_candidate,
    title_similarity,
)
from app.compliance.models import Control, Evidence, EvidenceSuggestion, Policy
from app.compliance.version_promotion import (
    accept_new_version,
    current_version_of,
    reconcile_evidence,
    version_history,
)
from app.core.dedupe import content_fingerprint, text_fingerprint
from app.core.models import File

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

UNRELATED = """Employee Travel Policy
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
            "full_name": "Version Tester",
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
) -> File:
    return File(
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


# --- reading what a document says about itself ------------------------


def test_a_document_that_states_its_version_is_believed() -> None:
    assert detect_version_label(V1) == "1.0"
    assert detect_version_label(V2) == "2.0"
    assert detect_version_label("Revision: 3") == "3"


def test_a_document_with_no_version_is_not_given_one() -> None:
    """Writing "1.0" on a document that never claimed it is putting words
    in its mouth."""
    assert detect_version_label("A policy with no version statement.") is None
    assert detect_version_label("") is None


def test_an_effective_date_is_read_where_stated() -> None:
    assert detect_effective_date(V2) == "August 2026"
    assert detect_effective_date("no dates here") is None


# --- the signals ------------------------------------------------------


def test_a_title_matches_through_the_words_that_decorate_it() -> None:
    """`Updated AI Policy August` and `AI Governance Policy` are the same
    document wearing different clothes."""
    assert title_similarity("Updated AI Policy August", "AI Governance Policy") > 0
    assert title_similarity("AI Governance Policy final", "AI Governance Policy") == 1.0
    assert title_similarity("Employee Travel Policy", "AI Governance Policy") == 0.0


def test_content_similarity_measures_shared_writing_not_shared_subject() -> None:
    """The contract is the floor the detector actually decides on.

    V2 is a heavy revision: of three sections it rewrites one, drops one
    and adds one, so only the Purpose survives word for word. That is
    close to the worst case a real version bump produces, and it still
    has to clear the floor comfortably while an unrelated policy from the
    same template stays far below it.
    """
    revision = content_similarity(V1, V2)
    coincidence = content_similarity(V1, UNRELATED)

    assert revision > CONTENT_FLOOR * 1.5
    assert coincidence < CONTENT_FLOOR / 2
    # Shared subject alone must not look anything like shared writing.
    assert revision > coincidence * 5
    assert content_similarity(V1, V1) == 1.0


def test_headings_are_compared_as_the_document_writes_them() -> None:
    assert heading_similarity(V1, V2) > 0.3
    assert heading_similarity(V1, UNRELATED) < 0.3


# --- confidence -------------------------------------------------------


def _score(uploaded_text: str, existing_text: str, **overrides) -> float:
    defaults = dict(
        uploaded_title="AI Governance Policy",
        uploaded_filename="AI Governance Policy.docx",
        uploaded_text=uploaded_text,
        uploaded_type="Policy",
        existing_title="AI Governance Policy",
        existing_filename="AI Governance Policy.docx",
        existing_text=existing_text,
        existing_type="Policy",
    )
    defaults.update(overrides)
    score, _ = score_candidate(**defaults)
    return score


def test_a_revised_version_of_the_same_policy_scores_high() -> None:
    assert _score(V2, V1, uploaded_version="2.0", existing_version="1.0") >= HIGH_CONFIDENCE


def test_a_different_filename_does_not_prevent_a_match() -> None:
    """§34: the filename is one signal and never the deciding one."""
    score = _score(
        V2,
        V1,
        uploaded_filename="Updated_AI_Governance_August.docx",
        uploaded_title="Updated AI Governance August",
        uploaded_version="2.0",
        existing_version="1.0",
    )
    assert score >= MEDIUM_CONFIDENCE


def test_an_unrelated_document_scores_low_however_it_is_named() -> None:
    """§35: `Employee_Travel_Policy.docx` must never be attached to the
    AI Governance Policy."""
    score = _score(
        UNRELATED,
        V1,
        uploaded_title="Employee Travel Policy",
        uploaded_filename="Employee_Travel_Policy.docx",
    )
    assert score < MEDIUM_CONFIDENCE


def test_a_shared_title_alone_is_not_enough() -> None:
    """Two policies from the same template share a name and a type. That
    is a coincidence, not a lineage."""
    score = _score(
        "Wholly different words about a wholly different subject entirely.",
        V1,
    )
    assert score < HIGH_CONFIDENCE


def test_a_filename_saying_v2_proves_nothing_by_itself() -> None:
    """§29: never create a version because the filename contains "v2"."""
    score = _score(
        UNRELATED,
        V1,
        uploaded_title="Employee Travel Policy v2",
        uploaded_filename="Employee_Travel_Policy_v2.docx",
    )
    assert score < MEDIUM_CONFIDENCE


# --- accepting a version ----------------------------------------------


async def test_accepting_a_version_supersedes_without_deleting(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§33 and §23: one logical document, two versions, nothing lost."""
    user_id, org_id = await _signup(client, "ver-accept@example.com", "Version Accept Org")
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

    assert v1.superseded_by_id == v2.id
    assert v2.supersedes_id == v1.id
    # Kept: "what did your policy say in March" is a question an auditor
    # asks.
    assert await db_session.get(File, v1.id) is not None

    chain = await version_history(db_session, organization_id=org_id, file_record=v1)
    assert [row.id for row in chain] == [v1.id, v2.id]
    assert (await current_version_of(db_session, file_record=v1)).id == v2.id


async def test_accepting_the_same_version_twice_changes_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§30: a retried acceptance must not fork the chain."""
    user_id, org_id = await _signup(client, "ver-retry@example.com", "Version Retry Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    db_session.add_all([v1, v2])
    await db_session.commit()

    for _ in range(3):
        await accept_new_version(
            db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
        )
        await db_session.commit()

    chain = await version_history(db_session, organization_id=org_id, file_record=v2)
    assert len(chain) == 2


# --- evidence reconciliation ------------------------------------------


async def _mapping(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    file_record: File,
    control_id: uuid.UUID,
    section: str,
    passage: str,
    status: str = "proposed",
    decided_by: uuid.UUID | None = None,
) -> EvidenceSuggestion:
    row = EvidenceSuggestion(
        organization_id=org_id,
        file_id=file_record.id,
        control_id=control_id,
        status=status,
        source_location=section,
        quoted_passage=passage,
        passage_hash=text_fingerprint(section, passage),
        quote_verified=True,
        decided_by=decided_by,
    )
    db.add(row)
    await db.flush()
    return row


async def test_an_unchanged_passage_keeps_its_human_approval(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§38 and §14. Asking somebody to re-approve text they already read
    is how a product teaches people to click Approve without reading."""
    user_id, org_id = await _signup(client, "ver-keep@example.com", "Version Keep Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    control = Control(organization_id=org_id, title="Govern AI use")
    db_session.add_all([v1, v2, control])
    await db_session.flush()

    passage = "This policy sets out how the company governs its use of artificial intelligence"
    await _mapping(
        db_session,
        org_id=org_id,
        file_record=v1,
        control_id=control.id,
        section="1. Purpose",
        passage=passage,
        status="approved",
        decided_by=user_id,
    )
    new = await _mapping(
        db_session,
        org_id=org_id,
        file_record=v2,
        control_id=control.id,
        section="1. Purpose",
        passage=passage,
    )
    await db_session.commit()

    report = await reconcile_evidence(
        db_session, organization_id=org_id, previous=v1, current=v2
    )
    await db_session.commit()

    assert report.unchanged == 1
    assert report.approvals_preserved == 1
    await db_session.refresh(new)
    assert new.status == "approved"
    assert new.decided_by == user_id


async def test_a_changed_passage_loses_its_approval_and_says_why(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§36 and §14. Somebody's name must not stay attached to wording they
    never saw."""
    user_id, org_id = await _signup(client, "ver-changed@example.com", "Version Changed Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    control = Control(organization_id=org_id, title="Monitor AI systems in production")
    db_session.add_all([v1, v2, control])
    await db_session.flush()

    await _mapping(
        db_session,
        org_id=org_id,
        file_record=v1,
        control_id=control.id,
        section="7. Monitoring",
        passage="AI systems should be monitored.",
        status="approved",
        decided_by=user_id,
    )
    new = await _mapping(
        db_session,
        org_id=org_id,
        file_record=v2,
        control_id=control.id,
        section="7. Monitoring",
        passage=(
            "Production AI systems are reviewed monthly for drift, incidents and "
            "material performance changes by the AI Governance Lead."
        ),
    )
    await db_session.commit()

    report = await reconcile_evidence(
        db_session, organization_id=org_id, previous=v1, current=v2
    )
    await db_session.commit()

    assert report.modified == 1
    assert report.approvals_reopened == 1
    await db_session.refresh(new)
    assert new.status == "proposed"
    assert new.decided_by is None
    assert "changed in the new version" in (new.routing_reason or "")


async def test_a_removed_section_stops_supporting_the_current_state(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17 and §37. A superseded policy is not what the organization does
    now, and the old evidence must not keep the coverage at 100%."""
    user_id, org_id = await _signup(client, "ver-removed@example.com", "Version Removed Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    control = Control(organization_id=org_id, title="Retain training data lawfully")
    db_session.add_all([v1, v2, control])
    await db_session.flush()

    old = await _mapping(
        db_session,
        org_id=org_id,
        file_record=v1,
        control_id=control.id,
        section="10. Retention",
        passage="Model training data is retained for two years and then deleted.",
        status="approved",
        decided_by=user_id,
    )
    await db_session.commit()

    report = await reconcile_evidence(
        db_session, organization_id=org_id, previous=v1, current=v2
    )
    await db_session.commit()

    assert report.removed == 1
    # Retained as history, attached to the version it came from.
    await db_session.refresh(old)
    assert old.file_id == v1.id
    assert old.status == "approved"


async def test_a_new_section_is_counted_as_added(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "ver-added@example.com", "Version Added Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    control = Control(organization_id=org_id, title="Name a human owner")
    db_session.add_all([v1, v2, control])
    await db_session.flush()

    await _mapping(
        db_session,
        org_id=org_id,
        file_record=v2,
        control_id=control.id,
        section="8. Human oversight",
        passage="Every production AI system has a named human owner who can halt it.",
    )
    await db_session.commit()

    report = await reconcile_evidence(
        db_session, organization_id=org_id, previous=v1, current=v2
    )
    assert report.added == 1


# --- policy integration -----------------------------------------------


async def test_a_new_version_keeps_one_managed_policy_and_reopens_approval(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19 and §20. The policy record is the same record; the approval is
    not — inheriting it would attach somebody's name to text they never
    read."""
    user_id, org_id = await _signup(client, "ver-policy@example.com", "Version Policy Org")
    v1 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V2)
    db_session.add_all([v1, v2])
    await db_session.flush()
    policy = Policy(
        organization_id=org_id,
        file_id=v1.id,
        title="AI Governance Policy",
        status="approved",
        version="1.0",
    )
    db_session.add(policy)
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
    assert len(policies) == 1, "a new version created a second policy record"
    await db_session.refresh(policy)
    assert policy.file_id == v2.id
    assert policy.status == "needs_review"


# --- the API ----------------------------------------------------------


async def test_a_document_reports_its_version_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "ver-api@example.com", "Version API Org")
    v1 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1, version_label="1.0")
    v2 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V2, version_label="2.0")
    db_session.add_all([v1, v2])
    await db_session.flush()

    created = await client.post(
        "/api/v1/knowledge/documents",
        json={"file_id": str(v2.id), "title": "AI Governance Policy.docx"},
    )
    document_id = created.json()["id"]
    await accept_new_version(
        db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
    )
    await db_session.commit()

    detail = (
        await client.get(f"/api/v1/compliance/documents/{document_id}/detail")
    ).json()
    versions = detail["versions"]
    assert [v["version_label"] for v in versions] == ["1.0", "2.0"]
    assert [v["status"] for v in versions] == ["superseded", "current"]
    assert detail["version_label"] == "2.0"


async def test_accepting_a_version_through_the_api_reports_what_changed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "ver-endpoint@example.com", "Version Endpoint Org")
    v1 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="Updated AI Policy August.docx", data=V2)
    control = Control(organization_id=org_id, title="Govern AI use")
    db_session.add_all([v1, v2, control])
    await db_session.flush()

    passage = "This policy sets out how the company governs its use of artificial intelligence"
    await _mapping(
        db_session,
        org_id=org_id,
        file_record=v1,
        control_id=control.id,
        section="1. Purpose",
        passage=passage,
        status="approved",
        decided_by=user_id,
    )
    await _mapping(
        db_session,
        org_id=org_id,
        file_record=v2,
        control_id=control.id,
        section="1. Purpose",
        passage=passage,
    )
    created = await client.post(
        "/api/v1/knowledge/documents",
        json={"file_id": str(v2.id), "title": "Updated AI Policy August.docx"},
    )
    document_id = created.json()["id"]
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/documents/{document_id}/accept-version",
        json={"supersedes_file_id": str(v1.id), "version_label": "2.0"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unchanged"] == 1
    assert body["approvals_preserved"] == 1
    assert body["version_label"] == "2.0"


async def test_a_document_cannot_supersede_itself(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "ver-self@example.com", "Version Self Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    db_session.add(v1)
    await db_session.flush()
    created = await client.post(
        "/api/v1/knowledge/documents",
        json={"file_id": str(v1.id), "title": "policy.docx"},
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/documents/{created.json()['id']}/accept-version",
        json={"supersedes_file_id": str(v1.id)},
    )
    assert response.status_code == 422


async def test_another_organizations_document_cannot_be_superseded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_id, owner_org = await _signup(client, "ver-owner@example.com", "Version Owner Org")
    theirs = _file(owner_org, owner_id, name="policy.docx", data=V1)
    db_session.add(theirs)
    await db_session.flush()
    await db_session.commit()

    user_id, org_id = await _signup(client, "ver-other@example.com", "Version Other Org")
    mine = _file(org_id, user_id, name="policy.docx", data=V2)
    db_session.add(mine)
    await db_session.flush()
    created = await client.post(
        "/api/v1/knowledge/documents",
        json={"file_id": str(mine.id), "title": "policy.docx"},
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/documents/{created.json()['id']}/accept-version",
        json={"supersedes_file_id": str(theirs.id)},
    )
    assert response.status_code == 404


async def test_declining_the_proposal_clears_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A guess the person answered. Asking again on every page load is how
    a product becomes something people click past."""
    user_id, org_id = await _signup(client, "ver-decline@example.com", "Version Decline Org")
    v1 = _file(org_id, user_id, name="AI Governance Policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="Employee Travel Policy.docx", data=UNRELATED)
    db_session.add_all([v1, v2])
    await db_session.flush()
    v2.version_candidate_id = v1.id
    v2.version_confidence = "medium"
    created = await client.post(
        "/api/v1/knowledge/documents",
        json={"file_id": str(v2.id), "title": "Employee Travel Policy.docx"},
    )
    await db_session.commit()

    detail = (
        await client.get(f"/api/v1/compliance/documents/{created.json()['id']}/detail")
    ).json()
    assert detail["version_candidate"] is not None

    response = await client.post(
        f"/api/v1/compliance/documents/{created.json()['id']}/separate-document"
    )
    assert response.status_code == 200, response.text
    assert response.json()["version_candidate"] is None

    await db_session.refresh(v2)
    assert v2.supersedes_id is None
    assert v2.version_candidate_id is None


async def test_evidence_is_never_moved_between_organizations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tenant isolation survives reconciliation: the query is scoped, so
    another organization's identical document contributes nothing."""
    owner_id, owner_org = await _signup(client, "ver-iso-a@example.com", "Version Iso A")
    other_id, other_org = await _signup(client, "ver-iso-b@example.com", "Version Iso B")

    mine_v1 = _file(owner_org, owner_id, name="policy.docx", data=V1)
    mine_v2 = _file(owner_org, owner_id, name="policy.docx", data=V2)
    theirs = _file(other_org, other_id, name="policy.docx", data=V1)
    control = Control(organization_id=other_org, title="Their control")
    db_session.add_all([mine_v1, mine_v2, theirs, control])
    await db_session.flush()

    await _mapping(
        db_session,
        org_id=other_org,
        file_record=theirs,
        control_id=control.id,
        section="1. Purpose",
        passage="This policy sets out how the company governs its use",
        status="approved",
        decided_by=other_id,
    )
    await db_session.commit()

    report = await reconcile_evidence(
        db_session, organization_id=owner_org, previous=mine_v1, current=mine_v2
    )
    assert report.unchanged == 0
    assert report.removed == 0

    survivor = (
        await db_session.execute(
            select(EvidenceSuggestion).where(EvidenceSuggestion.file_id == theirs.id)
        )
    ).scalars().first()
    assert survivor is not None
    assert survivor.status == "approved"


async def test_evidence_rows_are_not_duplicated_by_a_version(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§18: a new version must never fork the compliance state."""
    user_id, org_id = await _signup(client, "ver-nodupe@example.com", "Version No Dupe Org")
    v1 = _file(org_id, user_id, name="policy.docx", data=V1)
    v2 = _file(org_id, user_id, name="policy.docx", data=V2)
    control = Control(organization_id=org_id, title="Govern AI use")
    db_session.add_all([v1, v2, control])
    await db_session.flush()
    db_session.add_all(
        [
            Evidence(
                organization_id=org_id, file_id=v1.id, control_id=control.id, title="v1"
            ),
            Evidence(
                organization_id=org_id, file_id=v2.id, control_id=control.id, title="v2"
            ),
        ]
    )
    await db_session.commit()

    for _ in range(3):
        await accept_new_version(
            db_session, organization_id=org_id, previous=v1, current=v2, actor_user_id=user_id
        )
        await db_session.commit()

    rows = (
        (
            await db_session.execute(
                select(Evidence).where(
                    Evidence.organization_id == org_id, Evidence.control_id == control.id
                )
            )
        )
        .scalars()
        .all()
    )
    # One per version — the history — and no more, however many times the
    # acceptance runs.
    assert len(rows) == 2
