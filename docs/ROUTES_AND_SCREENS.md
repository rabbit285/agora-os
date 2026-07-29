# Routes and Screens

Full target screen inventory is spec §67 (Required Product Screens) and §6
(Application Navigation). This document tracks the frontend route map and
marks Phase 1 status per route. Legend: `[x]` implemented, `[~]` scaffolded
(page exists, minimal/placeholder content), `[ ]` not started.

## AUTH

| Route | Status |
|---|---|
| `/login` | [x] |
| `/signup` | [x] |
| `/invite/[token]` | [ ] |
| `/forgot-password` | [x] |
| `/reset-password/[token]` | [x] |
| `/verify-email/[token]` | [ ] |
| MFA challenge | [ ] |

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
| `/compliance` | [x] controls + risks + frameworks overview |
| `/compliance/controls/[id]` | [x] detail: requirements, assessments, evidence |

Not yet built (spec §67 lists these under Compliance): Framework-specific
dashboards (GDPR/EU AI Act individual views), Evidence Library standalone
page, AI Inventory/Assessment, Data Inventory/DPIA/DSAR, Vendors,
Questionnaires, Policies list page (API exists, no UI yet), Audits, Trust
Center, Regulatory Intelligence.

## SECURITY

| Route | Status |
|---|---|
| `/security` | [x] assets + findings + alerts + incidents overview |
| `/security/incidents/[id]` | [x] detail: status workflow, linked compliance risk |

Not yet built (spec §67 lists these under Security): standalone Asset
Detail page, Cloud Security / Identity Security dedicated views, Alert
Detail page, Security Policies. Incident workspace has a status workflow
but not the full Timeline/Affected Assets/Evidence/Communication/Root
Cause/Lessons Learned tab structure spec §19 describes.

## SALES

| Route | Status |
|---|---|
| `/sales` | [x] accounts + pipeline overview |
| `/sales/accounts/[id]` | [x] detail: contacts (suppression toggle), compose/send outreach, opportunities |

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
| `/settings/users` | [x] |
| `/settings/roles` | [~] read-only view |
| `/settings/ai-providers` | [~] shows configured/not-configured state |
| all other settings sub-pages (spec §67 SETTINGS group) | [ ] |

## App shell layout

`apps/web/app/(app)/layout.tsx` renders `AppSidebar` + `TopNavigation` +
`ModuleSwitcher` (spec §70–71) around every authenticated route. Unimplemented
modules still appear in the sidebar/module switcher but link to a "this
module isn't built yet" state rather than a broken 404 — never a fake
working page (spec §82).
