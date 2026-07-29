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
- The frontend renders a "Demo data" badge whenever the Copilot response's
  `provider == "demo"` (`apps/web/app/(app)/copilot/page.tsx`) — never
  presented as a live provider result (spec §I4).
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

## Retrieval and citations (spec §F4 — implemented)

`app/knowledge/retrieval.py::search_chunks` scores every one of an
organization's stored chunk embeddings against a query embedding with
cosine similarity (Python-side — see `docs/DECISIONS.md` ADR-0012, not a
native `pgvector` query) and returns the top matches, always scoped to
`organization_id` — a query can never cross a tenant boundary regardless
of what a caller asks for.

`app/ai/copilot.py::ask_copilot` is the retrieval-grounded Copilot (spec
section 9):

1. Embed the question (`ModelGateway.embed`).
2. `search_chunks` for the asking user's organization.
3. If nothing is found, answer honestly that there's no indexed content
   yet (`NO_EVIDENCE_MESSAGE`) rather than calling the model with no
   grounding and risking an unsupported answer (spec F4: "refuse or
   qualify when evidence is insufficient").
4. Otherwise build a prompt wrapping each retrieved chunk in a `<source>`
   block and call `ModelGateway.generate()`.
5. Citations attached to the response and to the `AiRun` row come from
   **what was retrieved in step 2**, never from anything the model claims
   about itself — an LLM asserting its own sources proves nothing.

`/api/v1/ai/copilot/ask` (`app/routers/ai.py`) is a thin wrapper around
this. The frontend `/copilot` page shows the answer, a "Demo data" badge
when unconfigured, and links back to the source document/chunk.

Not yet implemented: the intent router across modules (spec's cross-
functional Copilot examples — pulling from Compliance/Security/Sales
context, not just Knowledge), and organization-scoped knowledge-base
filtering in the UI (the API supports `knowledge_base_id` in
`search_chunks` already; nothing calls it yet since there's normally only
the one default "General" knowledge base).

## Prompt injection defense (spec §F5 — implemented, minimal)

`build_grounded_prompt` (`app/ai/copilot.py`) wraps every retrieved chunk
in an explicit `<source id="N">...</source>` block preceded by an
instruction that content inside those tags is untrusted data to quote or
summarize, never instructions to follow — tested in
`tests/test_copilot.py::test_build_grounded_prompt_delimits_untrusted_source_content`
with a chunk containing an actual injection attempt, asserting the
delimiters and warning text are present and ordered before the question.

This is a **prompt-level** defense only — it relies on the model
respecting the system framing. It is not a tool-execution allowlist or a
sandboxed sanitization pass, because Phase 2 has no AI-triggered tool
calls or actions yet (the Copilot only reads and answers). A tool
allowlist becomes necessary the moment the Copilot (or a workflow AI step)
can take an action based on retrieved content — track that against spec
F5 before shipping any such capability.
