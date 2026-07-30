"""Tests for the Knowledge-module completeness-audit backlog items: real
XLSX/HTML text extraction (spec §46 lists both as required formats, not
architecture-only like PPTX/OCR) and real reranking (spec §46 retrieval
quality) wired all the way from the AI gateway through Copilot's retrieval
step.
"""

from __future__ import annotations

import io
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import DemoAdapter, GenerateRequest, GenerateResult, ModelGateway
from app.ai.models import AiRun
from app.knowledge.models import DocumentChunk
from app.knowledge.parsing import extract_text


def _build_sample_xlsx() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Policies"
    sheet.append(["Policy", "Owner"])
    sheet.append(["Data Retention", "Compliance Team"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_extract_xlsx_returns_cell_text() -> None:
    data = _build_sample_xlsx()
    text = extract_text("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", data)
    assert "Policies" in text
    assert "Data Retention" in text
    assert "Compliance Team" in text


def test_extract_html_strips_tags_and_scripts() -> None:
    html = (
        b"<html><head><style>body{color:red}</style></head>"
        b"<body><script>alert('x')</script>"
        b"<h1>Refund Policy</h1><p>Refunds within 14 days.</p></body></html>"
    )
    text = extract_text("text/html", html)
    assert "Refund Policy" in text
    assert "Refunds within 14 days." in text
    assert "alert" not in text
    assert "color:red" not in text
    assert "<h1>" not in text


# --- Reranking --------------------------------------------------------


async def test_demo_adapter_rerank_scores_lexical_overlap() -> None:
    scores = await DemoAdapter().rerank(
        "refund policy",
        [
            "Our refund policy allows returns within 14 days.",
            "The weather today is sunny with a light breeze.",
        ],
    )
    assert scores[0] > scores[1]


async def test_gateway_rerank_logs_ai_run(db_session: AsyncSession) -> None:
    gateway = ModelGateway(adapter=DemoAdapter())
    org_id = uuid.uuid4()
    scores = await gateway.rerank(
        db_session,
        organization_id=org_id,
        requested_by=None,
        query="refund policy",
        documents=["Refunds within 14 days.", "Unrelated weather report."],
    )
    assert len(scores) == 2

    run = (
        await db_session.execute(
            select(AiRun).where(
                AiRun.organization_id == org_id, AiRun.task_type == "knowledge.rerank"
            )
        )
    ).scalar_one()
    assert run.provider == "demo"
    assert run.output == {"document_count": 2}


class _NoRerankAdapter:
    """A fake adapter whose rerank() is genuinely unimplemented, to prove
    ModelGateway.rerank() falls back to a real reranker (not a no-op) rather
    than propagating the error."""

    provider_name = "fake-no-rerank"

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        raise NotImplementedError

    async def generate_structured(self, request, schema):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def stream(self, request: GenerateRequest):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        raise NotImplementedError("This adapter cannot rerank.")


async def test_gateway_rerank_falls_back_to_demo_when_provider_cannot(
    db_session: AsyncSession,
) -> None:
    gateway = ModelGateway(adapter=_NoRerankAdapter())
    org_id = uuid.uuid4()
    scores = await gateway.rerank(
        db_session,
        organization_id=org_id,
        requested_by=None,
        query="refund policy",
        documents=["our refund policy is generous", "unrelated weather report today"],
    )
    assert scores[0] > scores[1]

    run = (
        await db_session.execute(
            select(AiRun).where(
                AiRun.organization_id == org_id, AiRun.task_type == "knowledge.rerank"
            )
        )
    ).scalar_one()
    assert run.provider == "demo"


async def test_reranking_promotes_lexically_relevant_chunk_over_embedding_noise(
    db_session: AsyncSession,
) -> None:
    """Constructs a case where the initial cosine-similarity order and the
    lexically-correct order disagree, and asserts reranking — not the raw
    embedding score — determines the final top result."""
    from app.ai.copilot import _retrieve_and_rerank

    org_id = uuid.uuid4()
    document_id = uuid.uuid4()

    query_embedding = [1.0, 0.0, 0.0]
    relevant_chunk = DocumentChunk(
        organization_id=org_id,
        document_id=document_id,
        chunk_index=0,
        content="Our refund policy allows returns within 14 days of purchase.",
        # Deliberately far from the query embedding — low cosine score.
        embedding=[0.0, 1.0, 0.0],
        token_count=10,
    )
    noise_chunk = DocumentChunk(
        organization_id=org_id,
        document_id=document_id,
        chunk_index=1,
        content="The quarterly office plant-watering schedule is attached.",
        # Deliberately close to the query embedding — high cosine score.
        embedding=[1.0, 0.0, 0.0],
        token_count=10,
    )
    db_session.add(relevant_chunk)
    db_session.add(noise_chunk)
    await db_session.flush()

    results = await _retrieve_and_rerank(
        db_session,
        organization_id=org_id,
        requested_by=None,
        question="What is our refund policy?",
        query_embedding=query_embedding,
        gateway=ModelGateway(adapter=DemoAdapter()),
        top_k=2,
    )

    assert results[0].chunk_id == relevant_chunk.id
    assert results[0].content.startswith("Our refund policy")
