"""Provider-neutral AI Model Gateway (spec sections F1, 57).

No caller outside this module talks to an AI provider SDK directly. Every
call is logged as an AiRun (docs/AI_ARCHITECTURE.md). The gateway never
writes to the database or calls external systems on the model's behalf
(spec F2) — callers get back structured data and decide what to do with it.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.models import AiRun
from app.config import settings

# Fixed so every embedding in the system is comparable regardless of which
# provider produced it (matches OpenAI's text-embedding-3-small). A column
# storing embeddings is defined once for this dimension — changing it later
# means re-embedding everything, not just swapping a config value.
EMBEDDING_DIMENSIONS = 1536


@dataclass
class GenerateRequest:
    task_type: str
    prompt: str
    prompt_template: str | None = None
    prompt_version: str | None = None
    input_classification: str = "internal"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerateResult:
    text: str
    model: str
    provider: str
    confidence: float | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)


class RerankScores(BaseModel):
    """Shape returned by an LLM-based reranker (spec §46 retrieval quality):
    one relevance score per input document, same order, 0.0-1.0."""

    scores: list[float]


def build_rerank_request(query: str, documents: list[str]) -> GenerateRequest:
    """Pure so the prompt shape can be unit tested without a provider —
    same reasoning as app.ai.copilot.build_grounded_prompt."""
    listing = "\n\n".join(f"[{i}] {doc}" for i, doc in enumerate(documents))
    prompt = (
        "Score how relevant each numbered passage below is to the query, on a "
        "scale from 0.0 (irrelevant) to 1.0 (highly relevant). Return exactly "
        f"{len(documents)} scores, in the same order as the passages.\n\n"
        f"Query: {query}\n\n{listing}"
    )
    return GenerateRequest(task_type="knowledge.rerank", prompt=prompt)


class ModelAdapter(Protocol):
    provider_name: str

    async def generate(self, request: GenerateRequest) -> GenerateResult: ...

    async def generate_structured(
        self, request: GenerateRequest, schema: type[BaseModel]
    ) -> BaseModel: ...

    # Deliberately a plain `def`, not `async def`: implementations are async
    # generators, whose *call* returns an AsyncIterator[str] directly rather
    # than a coroutine that resolves to one — this signature matches that
    # calling convention for Protocol structural typing.
    def stream(self, request: GenerateRequest) -> AsyncIterator[str]: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def rerank(self, query: str, documents: list[str]) -> list[float]: ...


class DemoAdapter:
    """Deterministic, clearly-labeled adapter used when no provider is
    configured. Never presented to end users as a live result — every
    AiRun this adapter produces has provider == "demo" and the frontend
    must render a "Demo data" badge whenever it sees that value
    (spec I4, C2)."""

    provider_name = "demo"

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        digest = hashlib.sha256(request.prompt.encode()).hexdigest()[:8]
        return GenerateResult(
            text=(
                f"[DEMO MODE — no AI provider configured] "
                f"Deterministic placeholder response for task '{request.task_type}' "
                f"(ref {digest})."
            ),
            model="demo-deterministic-v1",
            provider=self.provider_name,
            confidence=None,
            citations=[],
        )

    async def generate_structured(
        self, request: GenerateRequest, schema: type[BaseModel]
    ) -> BaseModel:
        result = await self.generate(request)
        # Best-effort: populate the first string field of the schema with
        # the demo text so structured-output callers still get a valid,
        # clearly-labeled object rather than a crash.
        fields = schema.model_fields
        payload: dict[str, Any] = {}
        for name, info in fields.items():
            if info.annotation is str:
                payload[name] = result.text
            elif info.is_required():
                payload[name] = None
        return schema.model_construct(**payload)

    async def stream(self, request: GenerateRequest) -> AsyncIterator[str]:
        result = await self.generate(request)
        for word in result.text.split(" "):
            yield word + " "

    async def embed(self, texts: list[str]) -> list[list[float]]:
        def _vec(text: str) -> list[float]:
            # Extend a single sha256 digest deterministically to
            # EMBEDDING_DIMENSIONS floats by re-hashing with a counter —
            # not a real embedding, just a stable fixed-width fingerprint.
            values: list[float] = []
            counter = 0
            seed = text.encode()
            while len(values) < EMBEDDING_DIMENSIONS:
                digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
                values.extend(b / 255.0 for b in digest)
                counter += 1
            return values[:EMBEDDING_DIMENSIONS]

        return [_vec(t) for t in texts]

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Real, deterministic lexical-overlap scoring — not a fabricated
        confidence value, just a simple algorithm rather than an LLM call
        (spec §82, No Fake Features: an honest simple implementation, not a
        fake sophisticated one)."""
        query_tokens = set(query.lower().split())
        if not query_tokens:
            return [0.0 for _ in documents]

        def _score(document: str) -> float:
            doc_tokens = set(document.lower().split())
            if not doc_tokens:
                return 0.0
            overlap = len(query_tokens & doc_tokens)
            return overlap / len(query_tokens)

        return [_score(doc) for doc in documents]


def build_adapter() -> ModelAdapter:
    """Select the configured provider, falling back to DemoAdapter.

    Missing keys never crash the app (spec C2) — they just mean AI features
    run in demo mode until credentials are added.
    """
    if settings.ai_provider == "anthropic" and settings.anthropic_api_key:
        from app.ai.adapters.anthropic import AnthropicAdapter

        return AnthropicAdapter(api_key=settings.anthropic_api_key)
    if settings.ai_provider == "openai" and settings.openai_api_key:
        from app.ai.adapters.openai import OpenAIAdapter

        return OpenAIAdapter(api_key=settings.openai_api_key)
    return DemoAdapter()


class ModelGateway:
    """Facade used by domain services. Wraps an adapter and logs every call."""

    def __init__(self, adapter: ModelAdapter | None = None) -> None:
        self._adapter = adapter or build_adapter()

    async def generate(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        requested_by: uuid.UUID | None,
        request: GenerateRequest,
        citations: list[dict[str, Any]] | None = None,
    ) -> GenerateResult:
        """`citations`, when given, overrides whatever the adapter itself
        returned. Citations should come from *retrieval* (which chunks were
        actually fetched and fed into the prompt), never from the model's
        own output — an LLM asserting its own sources proves nothing (spec
        F4). Callers doing RAG (see app.ai.copilot) pass their retrieval
        results here explicitly."""
        start = time.perf_counter()
        error: str | None = None
        result: GenerateResult | None = None
        try:
            result = await self._adapter.generate(request)
            return result
        except Exception as exc:  # noqa: BLE001 - logged into AiRun, then re-raised
            error = str(exc)
            raise
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            resolved_citations = (
                citations if citations is not None else (result.citations if result else [])
            )
            db.add(
                AiRun(
                    organization_id=organization_id,
                    requested_by=requested_by,
                    task_type=request.task_type,
                    provider=self._adapter.provider_name,
                    model=result.model if result else "unknown",
                    prompt_template=request.prompt_template,
                    prompt_version=request.prompt_version,
                    input_classification=request.input_classification,
                    output={"text": result.text} if result else None,
                    citations=resolved_citations,
                    confidence=result.confidence if result else None,
                    latency_ms=latency_ms,
                    policy_result="allowed" if error is None else "error",
                    error=error,
                )
            )
            await db.flush()

    async def embed(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        requested_by: uuid.UUID | None,
        task_type: str,
        texts: list[str],
    ) -> list[list[float]]:
        """Embed a batch of texts, logging one AiRun for the whole batch
        (not one per text — see docs/DECISIONS.md ADR-0008) rather than
        flooding ai_runs with a row per document chunk.

        Providers that don't support embeddings (e.g. Anthropic) fall back
        to the deterministic Demo embedder rather than failing the whole
        ingestion — the AiRun records which happened via `provider`.
        """
        start = time.perf_counter()
        provider_name = self._adapter.provider_name
        error: str | None = None
        try:
            vectors = await self._adapter.embed(texts)
        except NotImplementedError:
            provider_name = "demo"
            vectors = await DemoAdapter().embed(texts)
        except Exception as exc:  # noqa: BLE001 - logged into AiRun, then re-raised
            error = str(exc)
            raise
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            db.add(
                AiRun(
                    organization_id=organization_id,
                    requested_by=requested_by,
                    task_type=task_type,
                    provider=provider_name,
                    model=f"{provider_name}-embeddings",
                    input_classification="internal",
                    output={"chunk_count": len(texts)},
                    latency_ms=latency_ms,
                    policy_result="allowed" if error is None else "error",
                    error=error,
                )
            )
            await db.flush()
        return vectors

    async def rerank(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        requested_by: uuid.UUID | None,
        query: str,
        documents: list[str],
    ) -> list[float]:
        """Re-scores already-retrieved documents for relevance to `query`
        (spec §46). Falls back to the deterministic Demo lexical-overlap
        reranker — not a no-op — if the configured provider doesn't
        implement one, the same graceful-degradation pattern `.embed()`
        uses for Anthropic."""
        start = time.perf_counter()
        provider_name = self._adapter.provider_name
        error: str | None = None
        try:
            scores = await self._adapter.rerank(query, documents)
        except NotImplementedError:
            provider_name = "demo"
            scores = await DemoAdapter().rerank(query, documents)
        except Exception as exc:  # noqa: BLE001 - logged into AiRun, then re-raised
            error = str(exc)
            raise
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            db.add(
                AiRun(
                    organization_id=organization_id,
                    requested_by=requested_by,
                    task_type="knowledge.rerank",
                    provider=provider_name,
                    model=f"{provider_name}-rerank",
                    input_classification="internal",
                    output={"document_count": len(documents)},
                    latency_ms=latency_ms,
                    policy_result="allowed" if error is None else "error",
                    error=error,
                )
            )
            await db.flush()
        return scores
