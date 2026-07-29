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
| `/copilot` | [ ] |
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

## COMPLIANCE / SECURITY / SALES / SUPPORT / AUTOMATION

Not started — Phases 3–7 respectively. Routes will be added under
`apps/web/app/(app)/compliance`, `/security`, `/sales`, `/support`,
`/automation` matching the navigation tree in spec §6.

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
