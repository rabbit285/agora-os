# Routes and Screens

Full target screen inventory is spec §67 (Required Product Screens) and §6
(Application Navigation). This document tracks the frontend route map and
marks Phase 1 status per route. Legend: `[x]` implemented, `[~]` scaffolded
(page exists, minimal/placeholder content), `[ ]` not started.

## AUTH

| Route | Status |
|---|---|
| `/login` | [x] redirects to MFA challenge when the account has TOTP enabled |
| `/signup` | [x] |
| `/invite/[token]` | [x] accept an org invitation, creating or attaching the user |
| `/forgot-password` | [x] |
| `/reset-password/[token]` | [x] |
| `/verify-email/[token]` | [x] |
| MFA challenge (`/mfa-challenge`) | [x] TOTP code entry, gates `get_org_context` until verified |

## ONBOARDING

| Route | Status |
|---|---|
| `/onboarding/company` | [~] placeholder step |
| `/onboarding/goals` | [ ] |
| remaining onboarding steps (spec §68) | [ ] |

## CORE (app shell)

| Route | Status |
|---|---|
| `/` (Unified Dashboard) | [~] placeholder metrics |
| `/copilot` | [x] retrieval-grounded Q&A with citations |
| `/tasks` | [x] list + create |
| `/approvals` | [x] list + approve/reject |
| `/notifications` | [~] |
| Global search (`/search`) | [x] real tenant-scoped search across 16 entity types, reachable from an always-visible top-nav box |
| Global Create button | [ ] |

## KNOWLEDGE

| Route | Status |
|---|---|
| `/knowledge` | [x] list + upload (real XLSX/HTML extraction in addition to PDF/DOCX/TXT/MD/CSV) |
| `/knowledge/[id]` | [x] detail with chunk viewer |
| `/knowledge/graph` | [x] Organization Knowledge Graph explorer — click-through traversal over 20 entity types' real cross-module relationships |

## COMPLIANCE

| Route | Status |
|---|---|
| `/compliance` | [x] controls + risks + vendors + questionnaires + audits + Trust Center management + security reviews + AI system inventory + AI incidents + RoPA/DPIA/DSAR + data transfers + frameworks overview |
| `/compliance/controls/[id]` | [x] detail: requirements, assessments, evidence |
| `/compliance/vendors/[id]` | [x] detail: status workflow, risk assessment form, assessment history, evidence list |
| `/compliance/questionnaires/[id]` | [x] detail: status workflow, missing-answer count banner, add-question form, per-question suggest-answer/save-draft/approve actions |
| `/compliance/audits/[id]` | [x] detail: status workflow, add-finding form, findings list with severity/status badges, mark-remediated action |
| `/compliance/security-reviews/[id]` | [x] detail: gap count, approval status, sync/clear actions, linked questionnaire card |
| `/compliance/ai-systems/[id]` | [x] detail: status workflow, linked approval banner, assessments |
| `/compliance/ai-incidents/[id]` | [x] detail: status workflow, linked risk banner, linked response task banner, link to the AI system |
| `/compliance/dpias/[id]` | [x] detail: status workflow, linked approval banner (high-risk only), findings, link to a linked AI system |
| `/compliance/dsars/[id]` | [x] detail: status workflow, due date (overdue indicator), fulfilled date, notes |
| `/trust/[org_slug]` | [x] **genuinely public, no auth** — spec B4 Trust Center page: published categories, downloadable-document links, evidence-request submission form |

Not yet built (spec §67 lists these under Compliance): Framework-specific
dashboards (GDPR/EU AI Act individual views — `/compliance/frameworks/[id]`
covers the generic per-framework case), Evidence Library standalone page
(evidence upload/list lives inline on `/compliance` today), a standalone
Data Inventory/RoPA detail view (list-only today), Regulatory Intelligence.

## SECURITY

| Route | Status |
|---|---|
| `/security` | [x] Security Overview dashboard (9 live metrics + "Run cloud scan" button) + assets + findings + alerts + incidents |
| `/security/assets/[id]` | [x] detail: findings on this asset, incidents referencing this asset |
| `/security/alerts/[id]` | [x] detail: status workflow, related finding |
| `/security/incidents/[id]` | [x] detail: status workflow, linked compliance risk, linked response task, full incident workspace (Timeline + Communication log, Affected Assets linker, Root Cause/Lessons Learned editor) |
| `/security/policies` | [x] reuses `GET /compliance/policies` read-only (spec §80 — no duplicate policy store) |

Cloud Security / Identity Security (spec §15-16) have no dedicated
standalone views — findings from `app.secops.cloud_scanner` surface in the
existing Findings list (filterable by category) and the Overview
dashboard's Cloud Misconfigurations / Identity Issues tiles, consistent
with the category-discriminator design already used for the Findings
table rather than a fourth table.

## SALES

| Route | Status |
|---|---|
| `/sales` | [x] Sales Intelligence dashboard, accounts, leads, pipeline overview, Lead Finder button |
| `/sales/accounts/[id]` | [x] detail: contacts (suppression toggle), compose/send outreach, opportunities (with an "Onboarded as a Support customer" link once closed_won, and a deal-blocker link to `/compliance/security-reviews/[id]` once a security review exists), ICP score badge, Enrich button |
| `/sales/icp` | [x] ICP Builder — saving immediately rescans every Account |
| `/sales/leads/[id]` | [x] detail: linked account/contact, status workflow |
| `/sales/contacts/[id]` | [x] detail: linked account, outreach history, suppression toggle |
| `/sales/opportunities/[id]` | [x] detail: linked account, stage workflow, onboarding indicator |
| `/sales/sequences`, `/sales/sequences/[id]` | [x] Sequence list + Sequence Builder (steps, enrollments, enroll-a-contact) |
| `/sales/campaigns`, `/sales/campaigns/[id]` | [x] Campaign list + create + real stats (enrolled/sent/blocked/completed) |
| `/sales/inbox` | [x] Sales Inbox — outbound outreach status across all contacts (no inbound reply tracking, no real provider connected) |
| `/sales/meetings` | [x] Meeting CRUD + real AI Copilot-generated prep notes (Meeting Assistant) |

## SUPPORT

| Route | Status |
|---|---|
| `/support` | [x] analytics tiles (open tickets, resolution time, CSAT, QA score) + customers + ticket creation/list overview |
| `/support/tickets/[id]` | [x] detail: status workflow, linked security alert, linked sales lead (upsell signal), message thread, AI draft-reply + approval, QA review form |
| `/support/knowledge` | [x] Knowledge Base article create/list + publish toggle |
| `/support/ai-agent` | [x] AI Agent enable + auto-send-grounded-replies configuration |
| `/support/conversations` | [x] thread-first view over the same Ticket data, filtered to email/chat channels (spec's Conversations screen — not a duplicate store, see ADR-0017/ADR-0039) |

## AUTOMATION

| Route | Status |
|---|---|
| `/automation` | [x] workflow list + step-by-step create form |
| `/automation/workflows/[id]` | [x] detail: status governance, run now, run history with expandable step log |

Not yet built (spec §67 lists these under Automation): a visual
drag-and-drop Workflow Builder (React Flow), Workflow Templates gallery,
a dedicated Connections page, automation analytics dashboard. The current
create form is a structured list-based step editor, not the visual
builder.

## SETTINGS

| Route | Status |
|---|---|
| `/settings/organization` | [x] |
| `/settings/users` | [x] member list + invite-a-member form (email + role) + pending-invitations list with revoke |
| `/settings/security` | [x] email verification status/resend, TOTP MFA enroll/confirm/disable |
| `/settings/roles` | [~] read-only view |
| `/settings/ai-providers` | [~] shows configured/not-configured state |
| `/settings/integrations` | [x] provider catalog for 6 OAuth providers (permission preview of requested scopes before Connect, Not-configured badge), OAuth connections (health/scopes/sync history, refresh/disconnect/sync-now — sync polls a durable Temporal job to completion), webhook connections (create, copy URL/secret, link/unlink a workflow, received events) |
| all other settings sub-pages (spec §67 SETTINGS group) | [ ] |

## App shell layout

`apps/web/app/(app)/layout.tsx` renders `AppSidebar` + `TopNavigation` +
`ModuleSwitcher` (spec §70–71) around every authenticated route. Unimplemented
modules still appear in the sidebar/module switcher but link to a "this
module isn't built yet" state rather than a broken 404 — never a fake
working page (spec §82).
