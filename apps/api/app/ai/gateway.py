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
        return [1.0 / (i + 1) for i in range(len(documents))]


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
    ) -> GenerateResult:
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
                    citations=result.citations if result else [],
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
