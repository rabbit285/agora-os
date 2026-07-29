from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import DemoAdapter, ModelGateway
from app.core.models import File
from app.knowledge.chunking import chunk_text
from app.main import app

SAMPLE_TEXT = "This is a short sample document used to test the ingestion pipeline. " * 20


def test_chunk_text_splits_long_text_with_overlap() -> None:
    text = "a" * 2500
    chunks = chunk_text(text, chunk_size=1000, overlap=150)
    assert len(chunks) == 3
    assert all(len(c) <= 1000 for c in chunks)


def test_chunk_text_empty_returns_no_chunks() -> None:
    assert chunk_text("   ") == []


def test_chunk_text_rejects_overlap_gte_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=10, overlap=10)


async def _signup(client: AsyncClient, email: str, org_name: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Knowledge Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


async def _create_file(
    db_session: AsyncSession, *, organization_id, uploaded_by, content_type: str
) -> File:
    file_record = File(
        organization_id=organization_id,
        storage_key=f"org/{organization_id}/{uuid.uuid4()}/sample",
        original_filename="sample",
        content_type=content_type,
        size_bytes=len(SAMPLE_TEXT),
        uploaded_by=uploaded_by,
    )
    db_session.add(file_record)
    await db_session.flush()
    return file_record


async def test_create_document_registers_pending_and_starts_ingestion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "doc1@example.com", "Doc Org 1")
    file_record = await _create_file(
        db_session, organization_id=org_id, uploaded_by=user_id, content_type="text/plain"
    )

    response = await client.post(
        "/api/v1/knowledge/documents",
        json={"file_id": str(file_record.id), "title": "Sample Document"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["title"] == "Sample Document"

    kb_response = await client.get("/api/v1/knowledge/knowledge-bases")
    assert kb_response.status_code == 200
    assert any(kb["name"] == "General" for kb in kb_response.json())


async def test_ingest_document_produces_ready_status_and_chunks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.knowledge.service import ingest_document

    user_id, org_id = await _signup(client, "doc2@example.com", "Doc Org 2")
    file_record = await _create_file(
        db_session, organization_id=org_id, uploaded_by=user_id, content_type="text/plain"
    )
    create_doc = await client.post(
        "/api/v1/knowledge/documents", json={"file_id": str(file_record.id), "title": "Sample"}
    )
    document_id = uuid.UUID(create_doc.json()["id"])

    status = await ingest_document(
        db_session,
        document_id=document_id,
        file_bytes=SAMPLE_TEXT.encode(),
        gateway=ModelGateway(adapter=DemoAdapter()),
    )
    assert status == "ready"

    chunks_response = await client.get(f"/api/v1/knowledge/documents/{document_id}/chunks")
    assert chunks_response.status_code == 200
    chunks = chunks_response.json()
    assert len(chunks) >= 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["token_count"] > 0

    doc_response = await client.get(f"/api/v1/knowledge/documents/{document_id}")
    assert doc_response.json()["status"] == "ready"


async def test_ingest_document_unsupported_format_is_marked_not_faked(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.knowledge.service import ingest_document

    user_id, org_id = await _signup(client, "doc3@example.com", "Doc Org 3")
    file_record = await _create_file(
        db_session, organization_id=org_id, uploaded_by=user_id, content_type="image/png"
    )
    create_doc = await client.post(
        "/api/v1/knowledge/documents", json={"file_id": str(file_record.id), "title": "Image"}
    )
    document_id = uuid.UUID(create_doc.json()["id"])

    status = await ingest_document(
        db_session,
        document_id=document_id,
        file_bytes=b"\x89PNG\r\n\x1a\nfake-image-bytes",
        gateway=ModelGateway(adapter=DemoAdapter()),
    )
    assert status == "unsupported_format"

    doc_response = await client.get(f"/api/v1/knowledge/documents/{document_id}")
    body = doc_response.json()
    assert body["status"] == "unsupported_format"
    assert body["error"] is not None


async def test_document_from_other_org_returns_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "doc4@example.com", "Doc Org 4")
    file_record = await _create_file(
        db_session, organization_id=org_id, uploaded_by=user_id, content_type="text/plain"
    )
    create_doc = await client.post(
        "/api/v1/knowledge/documents", json={"file_id": str(file_record.id), "title": "Sample"}
    )
    document_id = create_doc.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(other_client, "doc5@example.com", "Doc Org 5")

    response = await other_client.get(
        f"/api/v1/knowledge/documents/{document_id}",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()
