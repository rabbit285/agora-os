"""One document, one detail page, one route to it.

A document is shown in six places — the library, the evidence library, a
control's evidence, a policy's current document, a search hit, a Copilot
citation — and every one of them used to decide for itself where clicking
went, or offered nowhere to click at all. The Copilot's answer was a
`/knowledge/<id>` link the web middleware rewrites to a 404.

These tests hold the routes together: every surface hands out the same
canonical href, composed server-side, and none of them can point at a
module the product has withdrawn.
"""

from __future__ import annotations

import re
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot import ask_copilot
from app.ai.gateway import DemoAdapter, ModelGateway
from app.compliance.models import (
    Control,
    ControlMapping,
    Evidence,
    EvidenceSuggestion,
    Framework,
    Requirement,
)
from app.core.models import File
from app.core.routes import DOCUMENT_ROUTE, RETIRED_ROUTE_PREFIXES
from app.knowledge.documents import readable_title
from app.knowledge.service import ingest_document

FILENAME = "10_Special_Category_Data_Processing_Policy.docx"

POLICY_TEXT = (
    "Special Category Data Processing Policy\n\n"
    "1. Purpose\n"
    + " ".join(
        ["This policy governs the processing of special category personal data."] * 12
    )
    + "\n\n5. Article 9 condition review\n"
    + " ".join(
        ["Each processing activity records its Article 9 condition and its owner."] * 12
    )
    + "\n\n8. Test processing activity record\n"
    + " ".join(["The record below is included to provide realistic test evidence."] * 12)
    + "\n"
).encode()

UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


async def _signup(client: AsyncClient, email: str, org_name: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Navigation Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


async def _upload(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    filename: str = FILENAME,
    index: bool = True,
) -> tuple[uuid.UUID, uuid.UUID | None]:
    """A file, and the indexed document made from it. Returns (file, document)."""
    file_record = File(
        organization_id=org_id,
        storage_key=f"org/{org_id}/{uuid.uuid4()}/{filename}",
        original_filename=filename,
        content_type="text/plain",
        size_bytes=len(POLICY_TEXT),
        uploaded_by=user_id,
        processing_status="ready",
        document_type="Policy",
        document_domain="Privacy / GDPR",
        extracted_characters=len(POLICY_TEXT),
    )
    db_session.add(file_record)
    await db_session.flush()

    if not index:
        await db_session.commit()
        return (file_record.id, None)

    created = await client.post(
        "/api/v1/knowledge/documents",
        json={"file_id": str(file_record.id), "title": filename},
    )
    assert created.status_code in (200, 201), created.text
    document_id = uuid.UUID(created.json()["id"])

    await ingest_document(
        db_session,
        document_id=document_id,
        file_bytes=POLICY_TEXT,
        gateway=ModelGateway(adapter=DemoAdapter()),
    )
    file_record.index_status = "indexed"
    await db_session.commit()
    return (file_record.id, document_id)


async def _evidence_chain(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    file_id: uuid.UUID,
) -> None:
    """A framework requirement, a control that serves it, and an approved
    piece of evidence from this document — the chain the detail page
    shows."""
    framework = Framework(key=f"gdpr-{uuid.uuid4().hex[:6]}", name="GDPR", description=None)
    db_session.add(framework)
    await db_session.flush()

    requirement = Requirement(
        framework_id=framework.id,
        reference_code="Art. 9",
        title="Processing of special categories of personal data",
        description=None,
    )
    control = Control(
        organization_id=org_id,
        title="Control processing of special category data",
        description=None,
    )
    db_session.add_all([requirement, control])
    await db_session.flush()

    db_session.add(ControlMapping(control_id=control.id, requirement_id=requirement.id))
    evidence = Evidence(
        organization_id=org_id,
        file_id=file_id,
        control_id=control.id,
        title="Article 9 condition review",
    )
    db_session.add(evidence)
    await db_session.flush()

    db_session.add(
        EvidenceSuggestion(
            organization_id=org_id,
            file_id=file_id,
            control_id=control.id,
            requirement_id=requirement.id,
            status="approved",
            confidence=1.0,
            source_location="5. Article 9 condition review",
            quoted_passage="Each processing activity records its Article 9 condition",
            evidence_type="policy_statement",
            quote_verified=True,
            evidence_id=evidence.id,
        )
    )
    await db_session.commit()


def _assert_canonical(href: str) -> None:
    assert href.startswith(f"{DOCUMENT_ROUTE}/"), href
    for prefix in RETIRED_ROUTE_PREFIXES:
        assert not href.startswith(prefix), f"{href} points at withdrawn {prefix}"


# --- the library row ---------------------------------------------------


async def test_a_document_row_carries_the_canonical_detail_route(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "nav-row@example.com", "Nav Row Org")
    file_id, document_id = await _upload(client, db_session, user_id=user_id, org_id=org_id)

    response = await client.get("/api/v1/compliance/documents")
    assert response.status_code == 200, response.text
    row = next(item for item in response.json() if item["id"] == str(file_id))

    assert row["href"] == f"{DOCUMENT_ROUTE}/{document_id}"
    assert row["document_id"] == str(document_id)
    _assert_canonical(row["href"])
    # The filename is still there — it is how somebody finds the file on
    # their own disk — but the row is named for the document.
    assert row["title"] == "Special Category Data Processing Policy"
    assert row["original_filename"] == FILENAME


async def test_a_document_with_no_indexed_copy_offers_no_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A link to a page that does not exist is worse than no link.

    Every attachment in the organization appears in this list, including
    ones never submitted for analysis; they have no detail page yet.
    """
    user_id, org_id = await _signup(client, "nav-nolink@example.com", "Nav No Link Org")
    file_id, _ = await _upload(
        client, db_session, user_id=user_id, org_id=org_id, index=False
    )

    response = await client.get("/api/v1/compliance/documents")
    row = next(item for item in response.json() if item["id"] == str(file_id))
    assert row["href"] is None
    assert row["document_id"] is None


# --- the detail page ---------------------------------------------------


async def test_the_detail_page_shows_the_document_and_what_it_evidences(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "nav-detail@example.com", "Nav Detail Org")
    file_id, document_id = await _upload(client, db_session, user_id=user_id, org_id=org_id)
    await _evidence_chain(db_session, org_id=org_id, file_id=file_id)

    response = await client.get(f"/api/v1/compliance/documents/{document_id}/detail")
    assert response.status_code == 200, response.text
    detail = response.json()

    # The header.
    assert detail["title"] == "Special Category Data Processing Policy"
    assert detail["filename"] == FILENAME
    assert detail["document_type"] == "Policy"
    assert detail["document_domain"] == "Privacy / GDPR"
    assert detail["processing_status"] == "ready"
    assert detail["index_status"] == "indexed"
    _assert_canonical(detail["href"])

    # The analysis: distinct things, not rows.
    assert detail["evidence_count"] == 1
    assert detail["control_count"] == 1
    assert detail["requirement_count"] == 1

    # The chain a reader follows: document -> passage -> control ->
    # requirement.
    item = detail["evidence"][0]
    assert item["source_location"] == "5. Article 9 condition review"
    assert item["control_title"] == "Control processing of special category data"
    assert item["framework_name"] == "GDPR"
    assert item["requirement_reference"] == "Art. 9"
    assert item["status"] == "approved"
    assert item["confidence"] == 1.0


async def test_the_detail_page_is_tenant_isolated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_id, owner_org = await _signup(client, "nav-owner@example.com", "Nav Owner Org")
    _, theirs = await _upload(client, db_session, user_id=owner_id, org_id=owner_org)

    await _signup(client, "nav-intruder@example.com", "Nav Intruder Org")
    response = await client.get(f"/api/v1/compliance/documents/{theirs}/detail")
    assert response.status_code == 404


async def test_an_unknown_document_is_a_404_not_a_broken_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "nav-missing@example.com", "Nav Missing Org")
    response = await client.get(f"/api/v1/compliance/documents/{uuid.uuid4()}/detail")
    assert response.status_code == 404


# --- one route, every surface -----------------------------------------


async def test_the_library_and_a_copilot_citation_open_the_same_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The acceptance case, at the API level.

    A row in the document library and a citation from the Copilot address
    one document, by one route. The citation additionally carries the
    passage it cited; strip that and the two are identical.
    """
    user_id, org_id = await _signup(client, "nav-same@example.com", "Nav Same Org")
    file_id, document_id = await _upload(client, db_session, user_id=user_id, org_id=org_id)

    listed = await client.get("/api/v1/compliance/documents")
    row = next(item for item in listed.json() if item["id"] == str(file_id))

    answer = await ask_copilot(
        db_session,
        organization_id=org_id,
        requested_by=user_id,
        question="What does our policy say about Article 9 conditions?",
        gateway=ModelGateway(adapter=DemoAdapter()),
    )
    assert answer.citations
    citation = answer.citations[0]

    assert citation.href.split("?")[0] == row["href"]
    assert f"{DOCUMENT_ROUTE}/{document_id}" == row["href"]
    # And the citation says where in the document, which the library row
    # has no reason to.
    assert "passage=" in citation.href


async def test_the_evidence_library_links_to_the_same_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "nav-evlib@example.com", "Nav Evidence Org")
    file_id, document_id = await _upload(client, db_session, user_id=user_id, org_id=org_id)
    await _evidence_chain(db_session, org_id=org_id, file_id=file_id)

    response = await client.get("/api/v1/compliance/evidence/by-document")
    assert response.status_code == 200, response.text
    group = next(item for item in response.json() if item["file_id"] == str(file_id))

    assert group["document_href"] == f"{DOCUMENT_ROUTE}/{document_id}"
    assert group["title"] == "Special Category Data Processing Policy"
    _assert_canonical(group["document_href"])


async def test_a_controls_evidence_links_to_the_same_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "nav-control@example.com", "Nav Control Org")
    file_id, document_id = await _upload(client, db_session, user_id=user_id, org_id=org_id)
    await _evidence_chain(db_session, org_id=org_id, file_id=file_id)

    control = (
        await db_session.execute(select(Control).where(Control.organization_id == org_id))
    ).scalars().first()
    assert control is not None

    response = await client.get(f"/api/v1/compliance/controls/{control.id}")
    assert response.status_code == 200, response.text
    evidence = response.json()["assessment"]["evidence"]
    assert evidence

    assert evidence[0]["document_href"] == f"{DOCUMENT_ROUTE}/{document_id}"
    _assert_canonical(evidence[0]["document_href"])


async def test_a_search_hit_opens_the_document_not_the_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "nav-search@example.com", "Nav Search Org")
    _, document_id = await _upload(client, db_session, user_id=user_id, org_id=org_id)

    response = await client.get("/api/v1/search", params={"q": "Special_Category"})
    assert response.status_code == 200, response.text
    hits = [r for r in response.json()["results"] if r["entity_type"] == "document"]
    assert hits, "the document was not found by search"

    assert hits[0]["href"] == f"{DOCUMENT_ROUTE}/{document_id}"
    _assert_canonical(hits[0]["href"])


async def test_no_surface_hands_out_a_link_into_a_withdrawn_module(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The regression that started this: `/knowledge/<id>`.

    Checked across every payload that names a document, because the bug
    was not in one component — it was that each of them decided its own
    route.
    """
    user_id, org_id = await _signup(client, "nav-retired@example.com", "Nav Retired Org")
    file_id, document_id = await _upload(client, db_session, user_id=user_id, org_id=org_id)
    await _evidence_chain(db_session, org_id=org_id, file_id=file_id)

    control = (
        await db_session.execute(select(Control).where(Control.organization_id == org_id))
    ).scalars().first()

    payloads = [
        (await client.get("/api/v1/compliance/documents")).text,
        (await client.get(f"/api/v1/compliance/documents/{document_id}/detail")).text,
        (await client.get("/api/v1/compliance/evidence/by-document")).text,
        (await client.get(f"/api/v1/compliance/controls/{control.id}")).text,
        (await client.get("/api/v1/search", params={"q": "Special_Category"})).text,
    ]

    for body in payloads:
        for prefix in RETIRED_ROUTE_PREFIXES:
            assert f'"{prefix}' not in body, f"a link into withdrawn {prefix} was handed out"


# --- naming ------------------------------------------------------------


def test_a_filename_reads_as_the_document_it_is() -> None:
    assert readable_title(FILENAME) == "Special Category Data Processing Policy"
    # An acronym the customer wrote correctly is left alone.
    assert readable_title("AI_Governance_Policy.docx") == "AI Governance Policy"
    # A name typed entirely in lower case gets a sentence capital, and
    # nothing more — title-casing would give "Gdpr Overview".
    assert readable_title("gdpr overview.md") == "Gdpr overview"
    assert readable_title("") == "Untitled document"
