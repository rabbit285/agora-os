# Product Vision — Agora Origin

## What this is

Agora Origin is a multi-tenant B2B SaaS "AI Business Operating System" for
European SMEs (10–500 employees). It unifies five business applications
around one company knowledge layer, one AI infrastructure, one governance
model, and one audit trail:

1. **AI Compliance** — GDPR, EU AI Act, ISO 27001, ISO 42001, SOC 2, NIS2, DORA
2. **AI Security Assistant** — asset inventory, cloud/identity security, vulnerabilities, incidents
3. **AI Sales Assistant** — ICP, lead finding, enrichment, outreach, pipeline
4. **AI Customer Support Automation** — inbox, AI agent, knowledge base, SLA, QA
5. **Business Process Automation** — no-code workflow builder with AI steps

Full detail: [`AGORA_ORIGIN_MASTER_SPEC.md`](AGORA_ORIGIN_MASTER_SPEC.md) is the
authoritative source of scope. This document and its siblings translate that
spec into an implementable architecture.

## Non-negotiable product principles

- **Trust is a feature, not an afterthought.** Progressive access: Stage 0 (no
  integration) → Stage 1 (read-only) → Stage 2 (scoped write) → Stage 3
  (approved automation) → Stage 4 (bounded auto-execution). See
  [`SECURITY_ARCHITECTURE.md`](SECURITY_ARCHITECTURE.md).
- **Compliance and Security govern the other modules**, not the reverse
  (spec §91–92). Sales, Support, and Automation call into governance checks
  before acting.
- **One shared platform**, not five disconnected products (spec §80). Every
  module reuses Organization, User, Task, Approval, Document, AI Run,
  Workflow, and Audit Log as shared primitives.
- **No fake features.** An incomplete integration shows `Not configured` /
  `Permission required` / `Demo data`, never a fabricated "Connected" or
  "Live" state (spec §82, §I4).
- **Human oversight on every high-impact AI action.** Read-only actions may
  run freely; Low/Moderate risk actions are governed by policy; High/Critical
  risk actions always require explicit approval (spec §B7, §55).

## Target customer

European SaaS/software/consulting/e-commerce/FinTech/HealthTech companies,
10–500 employees. Buyers: Founder/CEO/COO/CTO/CISO/DPO/Compliance
Manager/Head of Sales/Head of Support/Operations Manager.

## Positioning

> One secure AI operating system that helps European businesses stay
> compliant, sell more, support customers, automate operations, and safely
> adopt AI.

## Current build stage

See [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for exactly what
exists today. As of this writing the repository is in **Phase 1 — Platform
Foundation**: no domain modules (Compliance/Security/Sales/Support/Automation)
are implemented yet. Anyone picking this up should read
[`RESUME_BUILD.md`](RESUME_BUILD.md) first.
