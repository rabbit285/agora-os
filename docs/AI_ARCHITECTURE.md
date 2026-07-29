# AI Architecture

## Model Gateway (spec §F1, §57)

A single provider-neutral interface in `apps/api/app/ai/gateway.py`:

```python
class ModelGateway(Protocol):
    async def generate(self, request: GenerateRequest) -> GenerateResult: ...
    async def generate_structured(self, request: StructuredRequest, schema: type[BaseModel]) -> BaseModel: ...
    async def stream(self, request: GenerateRequest) -> AsyncIterator[str]: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def rerank(self, query: str, documents: list[str]) -> list[float]: ...
```

Provider adapters (`AnthropicAdapter`, `OpenAIAdapter`, `DemoAdapter`) all
implement this Protocol. Routing (task/sensitivity/cost/latency/region) is a
Phase 2+ concern; Phase 1 wires a single configured provider or the demo
adapter, chosen at gateway construction time from `settings.AI_PROVIDER`.

## Missing-key behavior (spec §C2)

`DemoAdapter` is deterministic and clearly labeled:

- `generate*` returns fixed, labeled-as-demo text keyed off a hash of the
  input so responses are stable across calls in tests.
- Every `AiRun` row written by the demo adapter has `provider = "demo"`.
- The frontend must render an "AI: Demo data" badge whenever
  `ai_run.provider == "demo"` — never presented as a live provider result
  (spec §I4). This badge is a Phase 2 UI item once Copilot screens exist;
  Phase 1 only guarantees the backend never conflates the two.
- If `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` are unset, gateway construction
  falls back to `DemoAdapter` rather than raising, so the app boots without
  paid keys (spec C2).

## Governance (spec §F2, §55, §56)

- The AI layer **never** writes to the database or calls external systems
  directly. It returns a structured proposal; a domain service or the
  workflow engine validates and executes it.
- Every AI call is logged as an `AiRun` (see `DATABASE_MODEL.md`) — task
  type, prompt version, model, input classification, output, citations,
  confidence, policy result. This is the substrate for the AI Action Log
  (spec §56) built in Phase 2.
- Risk classification (Read Only / Low / Moderate / High / Critical) and the
  approval-policy engine are introduced with the `Approval` primitive in
  Phase 1 and enforced per-module as each module's actions are implemented.

## Embeddings (spec §F1, §46 — implemented in Phase 2)

`ModelGateway.embed()` batches a list of texts, logs **one** `AiRun` per
batch call (not one per chunk — see `docs/DECISIONS.md` ADR-0008), and
returns fixed-width vectors: `EMBEDDING_DIMENSIONS = 1536`
(`app/ai/gateway.py`), matching OpenAI's `text-embedding-3-small` so every
embedding in the system is comparable regardless of which provider
produced it. `DemoAdapter.embed()` produces a deterministic 1536-float
fingerprint (repeated SHA-256 hashing, not a real embedding).

Providers that don't support embeddings (Anthropic) raise
`NotImplementedError`; the gateway catches that specifically and falls
back to `DemoAdapter` for that call rather than failing document
ingestion outright — the `AiRun.provider` field records which actually
happened, so this is never silently mislabeled as a real embedding.

## Retrieval and citations (spec §F4) — remaining Phase 2 work

Embeddings exist (above) but nothing queries them yet — no
cosine-similarity search, no RAG pipeline, no AI Copilot. Phase 2's scope
(spec's "Knowledge & AI Infrastructure") isn't finished until this exists:
`generate_structured` calls that use
retrieved context must attach `citations: list[Citation]` (`document_id`,
`chunk_id`, `location`) to the `AiRun` row, and refuse/qualify when
retrieval confidence is low.

## Prompt injection defense (spec §F5) — Phase 2+

Applies once external/uploaded content is retrievable by the AI (Phase 2
Knowledge module onward). Recorded here so the gateway's future `tool
allowlist` and `content sanitization` hooks are anticipated in the Protocol
shape rather than bolted on later.
