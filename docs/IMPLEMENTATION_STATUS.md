# Implementation Status

Legend: `[x]` Complete · `[~]` In Progress · `[ ]` Not Started · `[!]` Blocked

Last updated: 2026-07-29 (Phase 1 + Phase 2 complete — Knowledge ingestion, RAG retrieval, and AI Copilot — verified end-to-end)

## Platform

- [x] Monorepo structure
- [x] Docker Compose local infra (Postgres+pgvector, Redis, MinIO, Temporal) — all services healthy, verified via `docker compose ps`
- [x] Environment/config validation + `.env.example`
- [x] Core domain models (organizations, legal_entities, users, teams,
      memberships, roles, permissions)
- [x] Alembic migrations — generated, applied to real Postgres, `alembic check` reports no drift
- [x] Auth (signup/login/session/password reset) — verified via pytest and live curl smoke test
- [ ] MFA enforcement flow (schema present, flow not built)
- [x] Tenant-context middleware — verified: cross-org header spoofing rejected (test_tenant_isolation.py)
- [x] RBAC enforcement dependency — verified: employee role blocked from mutating actions (test_rbac.py)
- [x] Audit log (append-only at the application layer — see KNOWN_LIMITATIONS.md)
- [x] Tasks (shared primitive) — API + UI, live-tested
- [x] Approvals (shared primitive) — API + UI
- [x] Files (upload/download, signed URLs) — implemented, not live-tested against MinIO
- [x] Notifications (in-app only) — API + schema; no UI badge yet
- [x] Next.js app shell (sidebar/nav/module switcher stub) — production build verified
- [x] Seed script (Acme AI Technologies demo org) — idempotent, run twice successfully

## Knowledge

- [x] KnowledgeBase, Document, DocumentChunk models + migration
- [x] Document parsing: text/plain, text/markdown, text/csv, PDF, DOCX — genuine extractors, not stubs
- [x] Unsupported formats marked `unsupported_format` honestly, not faked as ready
- [x] Chunking (fixed-size with overlap) + embedding via AI gateway
- [x] Temporal `DocumentIngestionWorkflow` (durable, decoupled from the HTTP request)
- [x] `/api/v1/knowledge` router (knowledge bases, documents, chunks) — tenant-isolated, tested
- [x] Frontend: upload, list, detail pages with live status polling
- [x] Seed script uploads and fully ingests one real sample document
- [x] Similarity search (`search_chunks`, cosine similarity, tenant-scoped — see ADR-0012 for the not-pgvector-yet trade-off)
- [ ] Entity/relationship extraction (spec §11 knowledge graph) — not started

## AI

- [x] Model Gateway interface + Demo adapter
- [x] `AiRun` logging, including retrieval-sourced citations (not model-asserted)
- [x] `embed()` on the gateway (fixed 1536-dim, graceful demo fallback for non-embedding providers)
- [x] AI Copilot: retrieve → ground → generate → cite (`app/ai/copilot.py`), live-tested end to end
- [x] RAG / citations — implemented, tenant-isolated, tested
- [x] Prompt injection defenses — minimal (source delimiting + instruction, tested); no tool-execution allowlist yet (not needed until the Copilot can take actions)
- [ ] Cross-module intent router (Compliance/Security/Sales context beyond Knowledge) — not started

## Compliance

- [ ] Not started (Phase 3)

## Security

- [ ] Not started (Phase 4)

## Sales

- [ ] Not started (Phase 5)

## Support

- [ ] Not started (Phase 6)

## Automation

- [ ] Not started (Phase 7)

## Integrations

- [ ] Not started (Phase 9)

## Enterprise

- [ ] Not started (Phase 10)

## Testing

- [x] Tenant isolation tests (3 tests, passing)
- [x] RBAC denial tests (2 tests, passing)
- [x] Auth flow tests (8 tests, passing)
- [x] Knowledge module tests (7 tests: chunking, ingestion, unsupported format, tenant isolation)
- [x] Copilot tests (7 tests: cosine similarity, prompt injection framing, insufficient-evidence, retrieval + citations, tenant isolation)
- [x] 26/26 total, ruff+mypy strict clean
- [ ] Playwright E2E
- [ ] AI evaluation fixtures (Phase 3+)

## Infrastructure (AWS)

- [ ] Terraform bootstrap
- [ ] Network/security baseline
- [ ] Data services (RDS/ElastiCache/S3)
- [ ] Compute/edge (ECS/ALB/CloudFront/WAF)
- [ ] Observability
- [ ] CI workflows
- [ ] CD workflows
- [ ] Recovery validation

Only a local Docker Compose environment exists as of this writing. AWS
deployment has not been started — see `docs/RESUME_BUILD.md` for the exact
next steps and `docs/IMPLEMENTATION_PLAN.md` for phase ordering.

**Do not read this file as "the product is done."** It tracks a very large,
explicitly multi-phase build. As of this writing, Phase 1 (platform
foundation) and Phase 2 (Knowledge & AI Infrastructure) are complete;
Compliance, Security, Sales, Support, Automation (Phases 3–7), the
cross-module intent router beyond Knowledge, Phases 8–10, and the AWS
production deployment have not started.
