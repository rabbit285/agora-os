"""Understanding a document must not wait on the organization's setup.

The bug these pin: classification used to be a by-product of the
control-mapping call. A brand-new organization has no controls, so the
mapping half had nothing to answer, the combined call returned early, and
the classification went with it — leaving the very first thing a customer
does in the product as a row with a filename and nothing else. No type,
and therefore no Managed Policy.

"What is this document?" and "which of your controls does it evidence?"
are different questions, and only the second one needs controls.

Every assertion here reads the database. A pipeline that returns 200
while leaving a document unclassified has failed in the only way that
matters, and it fails silently.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.classification import DocumentClassification, classify_document
from app.compliance.evidence_ai import (
    DocumentAnalysis,
    ProposedMapping,
    suggest_evidence_mappings,
)
from app.compliance.models import Control, EvidenceSuggestion, Policy
from app.core.dedupe import content_fingerprint
from app.core.models import File

POLICY_TEXT = """AI Governance Policy
Version: 1.0
Effective: May 2026

1. Purpose
This policy sets out how the company governs its use of artificial intelligence
across every product and every team that operates one.

7. Monitoring
Production AI systems are reviewed monthly for drift, incidents and material
performance changes by the AI Governance Lead.
"""

ASSESSMENT_TEXT = """Vendor Privacy and Security Assessment

Vendor: Northwind Analytics Ltd

1. Scope
This assessment reviews Northwind Analytics as a processor of personal data
on our behalf, covering their security controls and privacy practices.
"""


class _StubClassifier:
    """Stands in for the model. Returns whatever the test scripted."""

    def __init__(self, document_type: str, document_domain: str = "AI Governance") -> None:
        self.document_type = document_type
        self.document_domain = document_domain
        self.calls = 0
        self.prompts: list[str] = []

    async def generate_structured(self, db, *, organization_id, requested_by, request, schema):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.prompts.append(request.prompt)
        return DocumentClassification(
            document_type=self.document_type,
            document_domain=self.document_domain,
        )


class _StubMapper:
    """The mapping call, which also volunteers a document type it must not keep."""

    def __init__(self, mappings: list[ProposedMapping] | None = None) -> None:
        self.mappings = mappings or []
        self.calls = 0

    async def generate_structured(self, db, *, organization_id, requested_by, request, schema):  # type: ignore[no-untyped-def]
        self.calls += 1
        return DocumentAnalysis(
            document_type="Something The Mapper Made Up",
            document_domain="Nonsense",
            mappings=self.mappings,
        )


async def _signup(client: AsyncClient, email: str, org: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Fresh Tester",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


def _file(org_id: uuid.UUID, user_id: uuid.UUID, *, name: str, text: str) -> File:
    return File(
        organization_id=org_id,
        storage_key=f"org/{org_id}/{uuid.uuid4()}/{name}",
        original_filename=name,
        content_type="text/plain",
        size_bytes=len(text),
        uploaded_by=user_id,
        processing_status="ready",
        content_hash=content_fingerprint(text.encode()),
    )


# --- classification does not depend on controls -----------------------


async def test_a_document_is_classified_with_no_controls_in_the_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3: the fresh-organization case, at its narrowest.

    Zero controls, zero frameworks, zero everything. The document still
    has to come back knowing what it is.
    """
    user_id, org_id = await _signup(client, "fresh-classify@example.com", "Fresh Classify")
    file_record = _file(org_id, user_id, name="AI_Governance_Policy.docx", text=POLICY_TEXT)
    db_session.add(file_record)
    await db_session.commit()

    controls = (
        await db_session.execute(
            select(func.count(Control.id)).where(Control.organization_id == org_id)
        )
    ).scalar_one()
    assert controls == 0, "this test is only meaningful with no controls"

    stub = _StubClassifier("AI Governance Policy")
    document_type = await classify_document(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        document_text=POLICY_TEXT,
        gateway=stub,  # type: ignore[arg-type]
    )
    await db_session.commit()

    assert document_type == "AI Governance Policy"
    await db_session.refresh(file_record)
    assert file_record.document_type == "AI Governance Policy"
    assert file_record.document_domain == "AI Governance"


async def test_the_classifier_is_never_told_about_controls(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§18: the prompt itself must not mention what it does not need.

    Mentioning controls or frameworks here is how this answer came to
    depend on an organization's setup in the first place.
    """
    user_id, org_id = await _signup(client, "fresh-prompt@example.com", "Fresh Prompt")
    file_record = _file(org_id, user_id, name="policy.docx", text=POLICY_TEXT)
    db_session.add(file_record)
    await db_session.commit()

    stub = _StubClassifier("AI Governance Policy")
    await classify_document(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        document_text=POLICY_TEXT,
        gateway=stub,  # type: ignore[arg-type]
    )

    prompt = stub.prompts[0].lower()
    for word in ("control", "framework", "requirement", "evidence"):
        assert word not in prompt, f"the classifier was told about {word}s"


async def test_classification_is_not_repeated_on_a_reprocess(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§16: asking a non-deterministic model the same question twice.

    Re-classifying on every reprocess would take whatever the model says
    this time — the same way re-extraction once turned two evidence items
    into four.
    """
    user_id, org_id = await _signup(client, "fresh-repeat@example.com", "Fresh Repeat")
    file_record = _file(org_id, user_id, name="policy.docx", text=POLICY_TEXT)
    db_session.add(file_record)
    await db_session.commit()

    stub = _StubClassifier("AI Governance Policy")
    for _ in range(3):
        await classify_document(
            db_session,
            organization_id=org_id,
            file_record=file_record,
            document_text=POLICY_TEXT,
            gateway=stub,  # type: ignore[arg-type]
        )
    await db_session.commit()

    assert stub.calls == 1, "the model was asked more than once"
    assert file_record.document_type == "AI Governance Policy"


async def test_a_shrug_is_recorded_as_absent_not_as_a_type(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """"Unclassified" is not a kind of document.

    Stored as absent so a later backfill tries again, rather than as text
    that every consumer downstream would have to know is not real.
    """
    user_id, org_id = await _signup(client, "fresh-shrug@example.com", "Fresh Shrug")
    file_record = _file(org_id, user_id, name="scan.docx", text="a b c d e f")
    db_session.add(file_record)
    await db_session.commit()

    await classify_document(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        document_text="a b c d e f",
        gateway=_StubClassifier("Unclassified", "General"),  # type: ignore[arg-type]
    )
    await db_session.commit()

    assert file_record.document_type is None


# --- Managed Policy without controls ----------------------------------


async def test_a_policy_gets_its_governance_record_with_no_controls(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4: the symptom the customer actually reported.

    `managed policies: 0` on a fresh organization's first upload.
    """
    from app.compliance.policy_governance import ensure_policy_for_document

    user_id, org_id = await _signup(client, "fresh-policy@example.com", "Fresh Policy")
    file_record = _file(org_id, user_id, name="AI_Governance_Policy.docx", text=POLICY_TEXT)
    db_session.add(file_record)
    await db_session.commit()

    await classify_document(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        document_text=POLICY_TEXT,
        gateway=_StubClassifier("AI Governance Policy"),  # type: ignore[arg-type]
    )
    policy = await ensure_policy_for_document(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        document_text=POLICY_TEXT,
        actor_user_id=user_id,
    )
    await db_session.commit()

    assert policy is not None
    policies = (
        await db_session.execute(select(Policy).where(Policy.organization_id == org_id))
    ).scalars().all()
    assert len(policies) == 1
    assert policies[0].file_id == file_record.id
    # Detected, never approved: the product cannot know who owns this.
    assert policies[0].status == "needs_review"
    assert policies[0].approved_by is None


async def test_a_non_policy_gets_no_governance_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§15: a Managed Policy for a vendor assessment would be noise in
    the one list that is supposed to be short."""
    from app.compliance.policy_governance import ensure_policy_for_document

    user_id, org_id = await _signup(client, "fresh-vendor@example.com", "Fresh Vendor")
    file_record = _file(org_id, user_id, name="assessment.docx", text=ASSESSMENT_TEXT)
    db_session.add(file_record)
    await db_session.commit()

    await classify_document(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        document_text=ASSESSMENT_TEXT,
        gateway=_StubClassifier(  # type: ignore[arg-type]
            "Vendor Security Assessment", "Vendor Management"
        ),
    )
    policy = await ensure_policy_for_document(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        document_text=ASSESSMENT_TEXT,
        actor_user_id=user_id,
    )
    await db_session.commit()

    assert policy is None
    assert file_record.document_type == "Vendor Security Assessment"
    count = (
        await db_session.execute(
            select(func.count(Policy.id)).where(Policy.organization_id == org_id)
        )
    ).scalar_one()
    assert count == 0


# --- mapping is the only stage that needs controls --------------------


async def test_mapping_returns_empty_with_no_controls_and_does_not_raise(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2: an empty mapping result is a fine answer. It just must not be
    the thing that stops everything else."""
    user_id, org_id = await _signup(client, "fresh-map@example.com", "Fresh Map")
    file_record = _file(org_id, user_id, name="policy.docx", text=POLICY_TEXT)
    db_session.add(file_record)
    await db_session.commit()

    mapper = _StubMapper()
    outcome = await suggest_evidence_mappings(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        file_bytes=POLICY_TEXT.encode(),
        actor_user_id=user_id,
        gateway=mapper,  # type: ignore[arg-type]
    )

    assert outcome.suggestions == []
    assert outcome.considered_controls == 0
    # And it did not spend a model call on a question with no answer.
    assert mapper.calls == 0


async def test_mapping_never_overwrites_the_recorded_classification(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3 and §18: classification has one owner.

    The mapping prompt still asks the model what the document is —
    knowing that makes it map better — but that answer is context for
    the call, not the record. Two sources for one fact is how they come
    to disagree.
    """
    user_id, org_id = await _signup(client, "fresh-owner@example.com", "Fresh Owner")
    file_record = _file(org_id, user_id, name="policy.docx", text=POLICY_TEXT)
    # A control, so the mapping call actually runs and gets its chance to
    # overwrite the classification.
    control = Control(
        organization_id=org_id,
        title="Monitoring of AI systems",
        description="Monitoring",
        status="not_started",
    )
    db_session.add_all([file_record, control])
    await db_session.commit()

    await classify_document(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        document_text=POLICY_TEXT,
        gateway=_StubClassifier("AI Governance Policy"),  # type: ignore[arg-type]
    )
    await db_session.commit()

    await suggest_evidence_mappings(
        db_session,
        organization_id=org_id,
        file_record=file_record,
        file_bytes=POLICY_TEXT.encode(),
        actor_user_id=user_id,
        gateway=_StubMapper(),  # type: ignore[arg-type]
    )
    await db_session.commit()

    await db_session.refresh(file_record)
    assert file_record.document_type == "AI Governance Policy"
    assert file_record.document_type != "Something The Mapper Made Up"


# --- the state the UI shows -------------------------------------------


async def test_no_controls_reads_as_a_state_not_a_failure(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5 and §10: three situations that all look like "0 mapped"."""
    user_id, org_id = await _signup(client, "fresh-state@example.com", "Fresh State")
    file_record = _file(org_id, user_id, name="policy.docx", text=POLICY_TEXT)
    file_record.document_type = "AI Governance Policy"
    db_session.add(file_record)
    await db_session.commit()

    response = await client.get("/api/v1/compliance/documents")
    assert response.status_code == 200, response.text
    row = response.json()[0]

    assert row["processing_status"] == "ready", "zero mappings is not a failed document"
    assert row["mapping_state"] == "no_controls"
    assert row["document_type"] == "AI Governance Policy"


async def test_with_controls_but_no_match_says_so_differently(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """"Nothing to map to yet" and "this matched nothing" are different
    answers, and the customer deserves to know which one they got."""
    user_id, org_id = await _signup(client, "fresh-nomatch@example.com", "Fresh No Match")
    file_record = _file(org_id, user_id, name="policy.docx", text=POLICY_TEXT)
    file_record.document_type = "AI Governance Policy"
    db_session.add(file_record)
    db_session.add(
        Control(
            organization_id=org_id,
            title="Access review",
            description="Access",
            status="not_started",
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/compliance/documents")
    assert response.json()[0]["mapping_state"] == "no_matches"


# --- reconciliation when controls arrive later ------------------------


async def test_controls_appearing_later_makes_an_old_document_eligible_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: no re-upload.

    `_should_extract` is what decides a document is worth another look.
    It has to say yes once controls exist that were not there when the
    document was read.
    """
    from app.compliance.evidence_ai import _should_extract

    user_id, org_id = await _signup(client, "fresh-later@example.com", "Fresh Later")
    file_record = _file(org_id, user_id, name="policy.docx", text=POLICY_TEXT)
    file_record.document_type = "AI Governance Policy"
    db_session.add(file_record)
    await db_session.flush()
    # Far enough in the future that a control created during this test is
    # unambiguously "older", so the last assertion tests the rule rather
    # than a race between two timestamps a microsecond apart.
    file_record.processed_at = datetime.now(UTC) + timedelta(seconds=1)
    await db_session.commit()
    await db_session.refresh(file_record)

    # Analysed, and it produced nothing because there was nothing to map
    # to. Worth another look on its own.
    assert await _should_extract(
        db_session, organization_id=org_id, file_record=file_record
    )

    # Once it *has* produced mappings, an unchanged control set means
    # there is nothing new to find.
    first_control = Control(
        organization_id=org_id,
        title="Monitoring",
        description="Monitoring",
        status="not_started",
    )
    db_session.add(first_control)
    await db_session.flush()
    db_session.add(
        EvidenceSuggestion(
            organization_id=org_id,
            file_id=file_record.id,
            control_id=first_control.id,
            source_location="7. Monitoring",
            quoted_passage="Production AI systems are reviewed monthly.",
            evidence_type="policy",
            status="proposed",
            confidence=0.9,
        )
    )
    await db_session.commit()
    assert not await _should_extract(
        db_session, organization_id=org_id, file_record=file_record
    )

    # A control created after the document was read is a real reason.
    later = Control(
        organization_id=org_id,
        title="Monitoring of AI systems",
        description="Monitoring",
        status="not_started",
    )
    db_session.add(later)
    await db_session.flush()
    later.created_at = datetime.now(UTC) + timedelta(seconds=30)
    await db_session.commit()
    assert await _should_extract(
        db_session, organization_id=org_id, file_record=file_record
    )


async def test_reconciling_with_no_controls_does_nothing_quietly(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: the hook fires on framework adoption, and adoption can be a
    deactivation. Nothing to map to is not an error."""
    from app.compliance.document_reconcile import map_documents_to_new_controls

    _, org_id = await _signup(client, "fresh-noop@example.com", "Fresh Noop")

    report = await map_documents_to_new_controls(
        org_id, session_factory=_factory(db_session)
    )

    assert report.examined == 0
    assert report.failed == 0


# --- backfill ---------------------------------------------------------


def _factory(db_session: AsyncSession):
    """Hand the reconcile passes the test's own session.

    They open their own session in production because they run as
    background work; here the transaction is the test's.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        yield db_session

    return factory


async def test_the_backfill_finds_documents_left_unclassified(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12: documents processed before this fix are still here.

    They parsed, they are indexed, and they have no type — so no Managed
    Policy, and no way to get one without something like this.
    """
    from app.compliance.document_reconcile import backfill_classification

    user_id, org_id = await _signup(client, "fresh-backfill@example.com", "Fresh Backfill")
    stranded = _file(org_id, user_id, name="AI_Governance_Policy.docx", text=POLICY_TEXT)
    stranded.document_type = None
    already = _file(org_id, user_id, name="known.docx", text=ASSESSMENT_TEXT)
    already.document_type = "Vendor Security Assessment"
    db_session.add_all([stranded, already])
    await db_session.commit()

    report = await backfill_classification(
        org_id, session_factory=_factory(db_session), dry_run=True
    )

    assert report.examined == 1, "only the unclassified one is a candidate"
    assert report.classified == 0, "a dry run writes nothing"
    await db_session.refresh(stranded)
    assert stranded.document_type is None


async def test_the_backfill_leaves_classified_documents_alone(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§11 and §12: running it twice must not re-decide anything."""
    from app.compliance.document_reconcile import backfill_classification

    user_id, org_id = await _signup(client, "fresh-bf2@example.com", "Fresh Backfill Two")
    classified = _file(org_id, user_id, name="policy.docx", text=POLICY_TEXT)
    classified.document_type = "AI Governance Policy"
    db_session.add(classified)
    await db_session.commit()

    report = await backfill_classification(
        org_id, session_factory=_factory(db_session), dry_run=False
    )

    assert report.examined == 0
    assert report.classified == 0
    assert classified.document_type == "AI Governance Policy"


# --- tenancy ----------------------------------------------------------


async def test_neither_pass_reaches_into_another_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: a bulk pass is exactly where a missing tenant filter hides."""
    from app.compliance.document_reconcile import (
        backfill_classification,
        map_documents_to_new_controls,
    )

    other_user, other_org = await _signup(client, "fresh-them@example.com", "Fresh Them")
    theirs = _file(other_org, other_user, name="theirs.docx", text=POLICY_TEXT)
    theirs.document_type = None
    db_session.add(theirs)

    mine_user, mine_org = await _signup(client, "fresh-me@example.com", "Fresh Me")
    db_session.add(
        Control(
            organization_id=mine_org,
            title="Mine",
            description="Mine",
            status="not_started",
        )
    )
    await db_session.commit()

    backfill = await backfill_classification(
        mine_org, session_factory=_factory(db_session), dry_run=True
    )
    assert backfill.examined == 0, "another organization's document was picked up"

    mapping = await map_documents_to_new_controls(
        mine_org, session_factory=_factory(db_session)
    )
    assert mapping.examined == 0

    await db_session.refresh(theirs)
    assert theirs.document_type is None


@pytest.mark.parametrize(
    ("processing_status", "has_controls", "mapping_count", "expected"),
    [
        ("ready", False, 0, "no_controls"),
        ("ready", True, 0, "no_matches"),
        ("ready", True, 3, "mapped"),
        ("ready", False, 2, "mapped"),
        ("parsing", False, 0, "not_analyzed"),
        ("failed", True, 0, "not_analyzed"),
    ],
)
def test_the_mapping_state_rule(
    processing_status: str, has_controls: bool, mapping_count: int, expected: str
) -> None:
    """§5: one rule, in one place, for three situations that look alike."""
    from app.routers.compliance import _mapping_state

    assert (
        _mapping_state(
            processing_status=processing_status,
            has_controls=has_controls,
            mapping_count=mapping_count,
        )
        == expected
    )
