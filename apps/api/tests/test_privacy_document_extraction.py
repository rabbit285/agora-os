"""Documents as a source of privacy records.

The reported bug: a privacy document uploaded, analysed, indexed for the
Copilot and mapped to nine controls, while Privacy → Processing
activities still said "Review suggestions (0)".

The cause was structural rather than a threshold or a UI count.
`privacy_suggestions.analyse` read `AISystem`, `Vendor`,
`ProcessingActivity` and `DataTransfer` — and never `File` or
`DocumentChunk`. Evidence mapping and the privacy register were two
pipelines, and only one of them was connected to documents.

These pin the connection: the facts a document states, the passage each
was read from, the draft it produces, and the rule that the legal
judgements are never extracted however plainly the document states them.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import privacy_extraction, privacy_suggestions
from app.compliance.models import PrivacySuggestion
from app.core.models import File
from app.knowledge.models import Document, DocumentChunk, KnowledgeBase

# The document the report was filed against, in the shape a processing
# description is actually written.
DOCUMENT = """Veyntra Privacy Test — AI Customer Support

Processing activity: AI Customer Support
Purpose: Respond to customer support requests
Processing owner: Customer Operations

Data subjects: Customers, prospective customers, customer employees
Personal data: Contact data, Support conversation content, Technical data, Attachments

AI system: AI Support Assistant
Vendor/processor: OpenAI
Destination: United States

Retention: 24 months for support-case records

The assistant performs systematic analysis of support conversations and
uses machine learning to draft replies. Some conversations may contain
special-category data where a customer volunteers health information.

We rely on legitimate interests for this processing and transfer under
Standard Contractual Clauses.
"""


async def _signup(client: AsyncClient, email: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _uploaded_and_analysed(
    db: AsyncSession,
    org_id: uuid.UUID,
    uploader: uuid.UUID,
    *,
    text: str = DOCUMENT,
    domain: str = "privacy",
    filename: str = "Veyntra_Privacy_Test_AI_Customer_Support.docx",
) -> File:
    """A document in the state the report describes: analysed and indexed.

    Built directly rather than through the upload pipeline, which needs a
    model to classify and map — the connection under test is what
    happens *after* that, and it should not depend on a provider being
    configured to run in CI.
    """
    file_record = File(
        organization_id=org_id,
        storage_key=f"{org_id}/{uuid.uuid4()}",
        original_filename=filename,
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        size_bytes=len(text),
        uploaded_by=uploader,
        processing_status="ready",
        document_domain=domain,
    )
    db.add(file_record)
    await db.flush()

    base = (
        await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.organization_id == org_id)
        )
    ).scalars().first()
    if base is None:
        base = KnowledgeBase(organization_id=org_id, name="Documents")
        db.add(base)
        await db.flush()

    document = Document(
        organization_id=org_id,
        knowledge_base_id=base.id,
        file_id=file_record.id,
        title=filename,
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
            embedding=[0.0],
            token_count=len(text.split()),
        )
    )
    await db.flush()
    return file_record


async def _uploader(db: AsyncSession, email: str) -> uuid.UUID:
    from app.identity.models import User

    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalars().first()
    assert user is not None
    return user.id


# --- what the document says ---------------------------------------------


def test_the_facts_a_processing_description_states() -> None:
    """§8: the expected candidate, field by field."""
    found = privacy_extraction.extract(
        DOCUMENT,
        file_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        title="Veyntra_Privacy_Test_AI_Customer_Support.docx",
    )

    values = {name: fact.value for name, fact in found.facts.items()}
    assert values["name"] == "AI Customer Support"
    assert values["purpose"] == "Respond to customer support requests"
    assert values["data_subjects"] == (
        "Customers, prospective customers, customer employees"
    )
    assert values["ai_system"] == "AI Support Assistant"
    assert values["vendor"] == "OpenAI"
    assert values["destination"] == "United States"
    assert values["retention"] == "24 months for support-case records"
    assert values["owner"] == "Customer Operations"

    assert found.data_categories == [
        "Contact data",
        "Support conversation content",
        "Technical data",
        "Attachments",
    ]
    assert found.destination_country == "US"
    assert found.usable is True


def test_every_fact_carries_a_quote_that_is_really_there() -> None:
    """Extraction that cannot show its source is invention.

    The same containment check `evidence_ai` applies to control
    mappings — which is what turns "it might be making this up" from a
    worry into a measurement.
    """
    found = privacy_extraction.extract(
        DOCUMENT, file_id=uuid.uuid4(), document_id=uuid.uuid4(), title="doc"
    )
    everything = list(found.facts.values()) + found.dpia_indicators
    assert everything
    for fact in everything:
        assert fact.quote
        assert privacy_extraction.quote_is_present(fact.quote, DOCUMENT), fact.field


def test_dpia_indicators_are_reported_with_their_evidence() -> None:
    """§3: indicators say the question is live, not that a DPIA is due."""
    found = privacy_extraction.extract(
        DOCUMENT, file_id=uuid.uuid4(), document_id=uuid.uuid4(), title="doc"
    )
    labels = {fact.value for fact in found.dpia_indicators}
    assert "Systematic monitoring or analysis" in labels
    assert "Special-category data" in labels
    assert "Innovative technology" in labels

    # The AI indicator is evidenced by the system field rather than by a
    # two-letter keyword that matches any heading.
    ai = next(
        fact for fact in found.dpia_indicators if fact.value == "Innovative technology"
    )
    assert ai.quote == "AI system: AI Support Assistant"


def test_no_legal_conclusion_is_ever_extracted() -> None:
    """§3: the document states a lawful basis and a mechanism plainly.

    Both are the organization's claim about a judgement, not the
    judgement — and a draft that carried them would answer the only
    questions the review exists to ask.
    """
    assert "legitimate interests" in DOCUMENT
    assert "Standard Contractual Clauses" in DOCUMENT

    found = privacy_extraction.extract(
        DOCUMENT, file_id=uuid.uuid4(), document_id=uuid.uuid4(), title="doc"
    )
    assert "legal_basis" not in found.facts
    assert "transfer_mechanism" not in found.facts

    draft = privacy_suggestions.draft_activity_from_document(found)
    assert draft.payload["legal_basis"] == privacy_suggestions.NEEDS_CONFIRMATION
    assert draft.payload["special_category"] is None


def test_a_document_that_only_mentions_privacy_proposes_nothing() -> None:
    """§7: an evidence mapping is not a processing activity.

    Nine approved mappings do not mean nine RoPA records, and a document
    with no processing described in it should produce none.
    """
    found = privacy_extraction.extract(
        "Our privacy notice explains your rights under the GDPR. "
        "Contact the DPO with any questions.",
        file_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        title="notice",
    )
    assert found.usable is False


# --- through the pipeline -------------------------------------------------


@pytest.mark.asyncio
async def test_an_analysed_privacy_document_produces_a_suggestion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§11: the reported flow, end to end and with nothing typed."""
    org_id = await _signup(client, "doc1@example.com")
    await _uploaded_and_analysed(
        db_session, org_id, await _uploader(db_session, "doc1@example.com")
    )
    await db_session.commit()

    result = await privacy_suggestions.analyse(db_session, organization_id=org_id)
    await db_session.commit()
    assert result.created == 1

    suggestions = (
        await client.get("/api/v1/compliance/privacy/suggestions")
    ).json()
    assert len(suggestions) == 1
    draft = suggestions[0]
    assert draft["title"] == "AI Customer Support"
    assert [source["type"] for source in draft["sources"]] == ["document"]
    assert "Veyntra_Privacy_Test" in draft["sources"][0]["label"]

    payload = draft["payload"]
    assert payload["purpose"] == "Respond to customer support requests"
    assert payload["ai_system_named"] == "AI Support Assistant"
    assert payload["vendor_named"] == "OpenAI"
    assert payload["destination_country"] == "US"
    assert payload["retention_stated"] == "24 months for support-case records"
    assert payload["legal_basis"] == "needs_confirmation"
    assert len(payload["dpia_indicators"]) >= 3
    # The quotes travel with the draft, so a reviewer checks it against
    # the document rather than trusting it.
    assert payload["quotes"]["purpose"]


@pytest.mark.asyncio
async def test_approving_it_creates_one_ropa_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "doc2@example.com")
    await _uploaded_and_analysed(
        db_session, org_id, await _uploader(db_session, "doc2@example.com")
    )
    await db_session.commit()
    await privacy_suggestions.analyse(db_session, organization_id=org_id)
    await db_session.commit()

    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]
    accepted = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "24 months"},
    )
    assert accepted.status_code == 200, accepted.text

    activities = (
        await client.get("/api/v1/compliance/processing-activities")
    ).json()
    assert len(activities) == 1
    assert activities[0]["name"] == "AI Customer Support"


@pytest.mark.asyncio
async def test_reanalysing_the_same_document_proposes_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: the identity is the document, so a re-read reconciles."""
    org_id = await _signup(client, "doc3@example.com")
    await _uploaded_and_analysed(
        db_session, org_id, await _uploader(db_session, "doc3@example.com")
    )
    await db_session.commit()

    for _ in range(3):
        await privacy_suggestions.analyse(db_session, organization_id=org_id)
        await db_session.commit()

    total = (
        await db_session.execute(
            select(func.count())
            .select_from(PrivacySuggestion)
            .where(PrivacySuggestion.organization_id == org_id)
        )
    ).scalar()
    assert total == 1


@pytest.mark.asyncio
async def test_a_non_privacy_document_is_not_mined_for_activities(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2: a contract is analysed for evidence too.

    Reading it for a processing activity produces noise a reviewer has
    to clear.
    """
    org_id = await _signup(client, "doc4@example.com")
    await _uploaded_and_analysed(
        db_session,
        org_id,
        await _uploader(db_session, "doc4@example.com"),
        domain="security",
        filename="Master_Services_Agreement.docx",
    )
    await db_session.commit()

    result = await privacy_suggestions.analyse(db_session, organization_id=org_id)
    await db_session.commit()
    assert result.created == 0


@pytest.mark.asyncio
async def test_a_generated_report_is_never_a_source_of_privacy_facts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A report Veyntra wrote is a result, not a source — the same rule
    that keeps it out of evidence analysis."""
    org_id = await _signup(client, "doc5@example.com")
    file_record = await _uploaded_and_analysed(
        db_session, org_id, await _uploader(db_session, "doc5@example.com")
    )
    file_record.artifact_type = "generated_output"
    file_record.origin_type = "audit_report"
    await db_session.commit()

    result = await privacy_suggestions.analyse(db_session, organization_id=org_id)
    await db_session.commit()
    assert result.created == 0


@pytest.mark.asyncio
async def test_documents_do_not_cross_organizations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "doc6@example.com")
    await _uploaded_and_analysed(
        db_session, org_id, await _uploader(db_session, "doc6@example.com")
    )
    await db_session.commit()

    other_id = await _signup(client, "doc7@example.com")
    result = await privacy_suggestions.analyse(db_session, organization_id=other_id)
    await db_session.commit()
    assert result.created == 0
    assert (await client.get("/api/v1/compliance/privacy/suggestions")).json() == []
