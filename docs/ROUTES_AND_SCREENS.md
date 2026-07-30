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
| Global search | [ ] |
| Global Create button | [ ] |

## KNOWLEDGE

| Route | Status |
|---|---|
| `/knowledge` | [x] list + upload |
| `/knowledge/[id]` | [x] detail with chunk viewer |

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
dashboards (GDPR/EU AI Act individual views), Evidence Library standalone
page, a standalone Data Inventory/RoPA detail view (list-only today),
Policies list page (API exists, no UI yet), Regulatory Intelligence.

## SECURITY

| Route | Status |
|---|---|
| `/security` | [x] assets + findings + alerts + incidents overview |
| `/security/incidents/[id]` | [x] detail: status workflow, linked compliance risk, linked response task |

Not yet built (spec §67 lists these under Security): standalone Asset
Detail page, Cloud Security / Identity Security dedicated views, Alert
Detail page, Security Policies. Incident workspace has a status workflow
but not the full Timeline/Affected Assets/Evidence/Communication/Root
Cause/Lessons Learned tab structure spec §19 describes.

## SALES

| Route | Status |
|---|---|
| `/sales` | [x] accounts + pipeline overview |
| `/sales/accounts/[id]` | [x] detail: contacts (suppression toggle), compose/send outreach, opportunities (with an "Onboarded as a Support customer" link once closed_won, and a deal-blocker link to `/compliance/security-reviews/[id]` once a security review exists) |

Not yet built (spec §67 lists these under Sales): ICP Builder, Lead
Finder, Lead Detail, Contact Detail (standalone), Sequences/Sequence
Builder, Campaigns, Sales Inbox, Meetings, Opportunity Detail (standalone),
Sales Intelligence.

## SUPPORT

| Route | Status |
|---|---|
| `/support` | [x] customers + ticket creation/list overview |
| `/support/tickets/[id]` | [x] detail: status workflow, linked security alert, linked sales lead (upsell signal), message thread |

Not yet built (spec §67 lists these under Support): Conversations
(separate from Tickets), AI Agent configuration, Knowledge Base standalone
management UI (API exists, no dedicated page yet), QA scoring dashboard,
CSAT reporting, support analytics.

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
