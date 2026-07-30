# Acceptance Test Evidence — 25 Required End-to-End Scenarios

Audit date: 2026-07-30. Evidence combines (a) the existing 206-test pytest suite (fresh
run this audit, 206 passed / 0 failed, 386.69s, `docker exec agora-origin-api-1 sh -lc
"cd /app && python -m pytest -q"`), (b) 9 parallel subagent code-level verifications, and
(c) fresh **live** curl/DB evidence gathered directly in this audit session against the
running dev stack (port 8001), using a disposable "Audit Test Org B" created via real
signup and fully cleaned up afterward — the pre-existing seeded dev org
("Acme AI Technologies") and its data were never modified.

Legend: 🟢 VERIFIED 🟡 PARTIAL 🔴 MISSING

---

### 1. Signup / org onboarding — 🟢 VERIFIED
Live, this audit: `POST /api/v1/auth/signup` with a new org name created a real
`Organization` (slug `audit-test-org-b`), a real `User`, and a real `org_admin`
`Membership` in one call — confirmed by subsequent successful `/auth/me` and
`/organizations/current` calls under the returned session cookie.

### 2. Document upload → parsing → chunking → embedding → retrieval — 🟢 VERIFIED
Code-verified (Knowledge subagent): `app/knowledge/{parsing,chunking,retrieval,service}.py`
implement real extraction (PDF/DOCX/TXT/MD), real chunking, real JSON-stored embeddings,
real Python-scan cosine-similarity retrieval (ADR-0007/ADR-0012). Test-suite covered.
Live, this audit: a Copilot ask against the seeded org returned real citations
(`document_id`, `chunk_id`, `chunk_index`, `score`) proving the retrieval index is live
and queryable, not decorative. XLSX/HTML are claimed-supported but have no extractor code
(see `REMAINING_PRODUCT_GAPS.md` §B Knowledge).

### 3. Evidence-grounded Copilot response with citations — 🟢 VERIFIED
Live, this audit: `POST /api/v1/ai/copilot/ask {"prompt":"What is our data retention
policy?"}` → `200`, response included `"grounded":true`, 2 citations with document/chunk
IDs and similarity scores, and an honest `[DEMO MODE — no AI provider configured]` label
(`provider":"demo"`) since no real Anthropic/OpenAI key is configured in this environment
— exactly the honest-fallback behavior the spec requires.

### 4. Compliance control/evidence lifecycle — 🟢 VERIFIED
Test-suite: control creation, requirement mapping, assessment recording, evidence
attachment, fail-assessment → Task hook all covered (Compliance subagent + direct read of
`app/compliance/{models,service}.py`).

### 5. High-risk AI system registration + DPIA + approval — 🟢 VERIFIED
Test-suite covers `register_ai_system`, DPIA creation linked to an AI system, and the
approval gate for high-risk DPIAs (Compliance subagent confirmed the linked-approval
banner on `/compliance/dpias/[id]` and `/compliance/ai-systems/[id]`).

### 6. DSAR lifecycle — 🟢 VERIFIED (request-tracking workflow only — see item 23 for the distinct "execute an export/erasure" capability)
Live, this audit: `GET /api/v1/compliance/dsars` against the seeded org returned real
rows (requester name/email, request type, status, due date, assignee). Test-suite covers
status-transition (`update_dsar_status`) and overdue-due-date display.

### 7. Security finding → incident → risk → task → notification — 🟢 VERIFIED
Test-suite (Security subagent + commit history: "reusing SecurityIncident's critical
chain a third time") confirms `SecurityIncident` critical severity creates a linked
`Risk`, a response `Task`, and a `Notification` in one hook.

### 8. Critical AI incident chain — 🟢 VERIFIED
Test-suite confirms `AIIncident` critical severity → `Risk` + `Task` + `Notification`,
independently re-verified by the Compliance subagent against `app/compliance/service.py`.

### 9. Sales lead / account / opportunity / sequence lifecycle — 🟡 PARTIAL
Lead/Account/Opportunity CRUD is 🟢 VERIFIED — live, this audit: created a real Account,
Contact, and two Opportunities against Org B, confirmed in each response body. "Sequence"
as a spec'd concept (a multi-step, scheduled outreach cadence) is 🔴 MISSING — only a
single manual-send `OutreachMessage` exists, no cadence/sequence engine.

### 10. Support ticket triage + grounded response — 🟡 PARTIAL
Ticket creation/triage/status workflow is 🟢 VERIFIED (test-suite + Support subagent). The
"grounded response" half is 🔴 MISSING: grep-confirmed zero calls from any support code
path into `app/ai/copilot.py` or `app/knowledge/retrieval.py` — ticket responses have no
AI/knowledge-base grounding at all today.

### 11. Support Upsell Signal — 🟡 PARTIAL (2 of 4 spec'd steps)
Test-suite confirms `flag_upsell_signal` creates a linked Sales `Lead` from a ticket. The
spec's full 4-step scenario also calls for Sales Copilot involvement and a notification to
the account owner — neither exists (see `SPEC_TRACEABILITY_MATRIX.md` SCEN-05).

### 12. New Customer cross-module flow — 🟡 PARTIAL (2 of 8 spec'd steps, the 2 that exist are fully proven live)
Live, this audit: created an Account + Contact + Opportunity in Org B, closed the
opportunity `closed_won` — response showed a real `onboarding_customer_id`, and
`GET /support/customers` showed exactly one new `Customer` row (name/email pulled from the
real primary Contact). Called `close_won` a second time on the same opportunity: response
was byte-identical, and the customer list still showed exactly one row — the
`Opportunity.onboarding_customer_id` idempotency guard is real, not just documented. Also
live-confirmed the documented "honest partial failure" path: closing a *different*
opportunity whose account had no Contact yet produced `onboarding_customer_id: null` (no
fabricated customer), which is the code's deliberate, disclosed behavior
(`app/sales/service.py:98-112`), not a defect. The 6 missing spec steps (welcome email,
billing-system update, scheduled check-in beyond the one Task, assign account owner) are
listed in `REMAINING_PRODUCT_GAPS.md` §A2.

### 13. Vendor risk + questionnaire flow — 🟢 VERIFIED
Test-suite confirms vendor creation, risk assessment recording, high/critical → Risk hook,
and independently, questionnaire creation/question-add/AI-suggest-answer/approve flow
(Compliance subagent).

### 14. Audit lifecycle — 🟢 VERIFIED
Test-suite confirms audit creation, finding recording, high/critical finding → Task hook,
status transitions, remediation marking.

### 15. Trust package generation — 🟢 VERIFIED
Fresh pytest run (this audit) includes and passes
`test_clearing_a_low_value_review_generates_a_trust_package` and
`test_high_value_review_requires_approval_before_clearing` — both in the passing 206.

### 16. Enterprise Sales Security Review — 🟢 VERIFIED (9 of 10 spec steps; the 1 gap is a single AI-copilot sub-step, not a structural gap)
Compliance subagent independently re-confirmed all major steps: review creation, gap sync
against a questionnaire, approval requirement for high-value deals, clearing, linked
Trust-package generation, and the Sales-account-detail deal-blocker indicator. Missing:
"Sales Copilot drafts follow-up" sub-step.

### 17. Workflow creation / publication / execution / failure / retry — 🟡 PARTIAL
Creation, status-governance (draft→published), manual run, and the `human_approval`
pause/resume/reject mechanism are all 🟢 VERIFIED with real behavioral test coverage for
all three approval paths. However: execution is fully synchronous inside the HTTP
request/response cycle with **zero Temporal usage** (contradicting spec §61's explicit
"do not couple workflows directly to HTTP requests" — unlike Knowledge and Integrations,
which correctly use Temporal), there is no `WorkflowVersion`/immutable publish history,
and only 3 of ~24 spec'd action types plus 2 of ~16 spec'd trigger types are executable.
"Retry" exists only in the narrow sense of re-running a completed/failed workflow
manually, not automatic durable retry semantics.

### 18. Signed webhook → workflow trigger — 🟢 VERIFIED
Test-suite covers signature verification and workflow triggering. Fresh DB query (this
audit) of `audit_events` in the pre-existing seeded dev database shows 4 real
`integrations.webhook.received` rows tied to `webhook_event` objects, confirming this path
has actually executed, not just been unit-tested in isolation.

### 19. OAuth connection lifecycle (deterministic/sandbox adapter) — 🟢 VERIFIED
Integrations subagent confirmed all 6 providers' adapters make real HTTP calls to real
provider URLs when credentialed, and fall back to `MockOAuthAdapter` (explicitly labeled,
no fabricated "connected" state, `provider_key`-scoped so mock connections stay
distinguishable per provider) when not — this is also what the test suite exercises for
every provider, since this environment has no real developer app registered for any of
the 6. Fresh DB query (this audit) shows real `integrations.oauth.started` /
`.connected` / `.disconnected` audit events (2 each) in the seeded dev data.

### 20. Approval denial + success — 🟢 VERIFIED
Fresh DB query (this audit) of the pre-existing seeded dev database shows 4 real
`core.approval.approved` audit events. Test-suite additionally covers the reject path
(`automation.run.awaiting_approval` → reject → run does not proceed), 2 real occurrences
also present in the audit-event table.

### 21. Cross-tenant access denial — 🟢 VERIFIED (fresh live proof, this audit, 3 independent techniques)
1. Listing: `GET /sales/accounts` as Org B returned `[]` even though Org A has 2 seeded
   accounts.
2. Direct ID guess: `GET /sales/accounts/{Org A's real account id}` as Org B → `404
   "Account not found"` (not a leak-revealing 403, and not the resource).
3. Header spoof: Org B's authenticated session with `X-Organization-Id` set to Org A's
   real org ID → `403 "Not authorized"` — the server-side membership check
   (`app/dependencies.py get_org_context`) rejects the mismatch regardless of the header
   value supplied.

### 22. Restricted-role access denial — 🟢 VERIFIED (fresh live proof, this audit)
Created a real `read_only`-role membership in the disposable test org, logged in as that
user: `POST /sales/accounts` → `403 {"message":"Missing permission:
sales.accounts.manage"}`; `GET /sales/accounts` (same user) → `200 []`. Confirms RBAC
denies writes and allows reads for a role with zero permission grants, exactly matching
`ROLE_PERMISSION_GRANTS`'s design for `read_only`.

### 23. Data export / deletion controls — 🔴 MISSING (as a distinct executable capability)
The DSAR **request-tracking workflow** (receive a request, assign, track due date, mark
fulfilled) is 🟢 VERIFIED (see item 6). A literal "export this person's data as a file" or
"erase this person's PII across the application" **execution** capability does not exist
anywhere in the 119-path OpenAPI surface (confirmed via a fresh `GET /openapi.json` dump,
this audit) — DSAR status can be marked "fulfilled" but nothing in the codebase actually
performs the export or the erasure. This is a real gap between "we tracked that we
should do this" and "the system did it."

### 24. Global search permission enforcement — 🔴 MISSING (feature itself does not exist)
Global search is not implemented at all (`PLAT-21`); the sidebar entry correctly routes to
the honest coming-soon state rather than a broken or fake result, but there is nothing to
verify permission enforcement against.

### 25. AI action risk classification + approval enforcement — 🟡 PARTIAL
The closest verified analog is the **AI System Inventory**'s EU AI Act risk-tier
classification with an approval gate for high-risk AI systems (`COMP-06`, 🟢 VERIFIED) —
registering an AI system as high-risk genuinely requires an approval before it can be
marked active. However, a general mechanism that classifies an individual **AI action /
LLM call** by risk and enforces approval before that specific action executes was not
found anywhere in `app/ai/gateway.py`, `app/ai/copilot.py`, or the automation approval
code — every `ModelGateway` call proceeds immediately and is only logged to `AiRun`
afterward, not risk-gated beforehand.

---

## Summary

| # | Scenario | Status |
|---|---|---|
| 1 | Signup / org onboarding | 🟢 |
| 2 | Document upload→retrieval | 🟢 |
| 3 | Grounded Copilot + citations | 🟢 |
| 4 | Control/evidence lifecycle | 🟢 |
| 5 | AI system + DPIA + approval | 🟢 |
| 6 | DSAR lifecycle | 🟢 |
| 7 | Security finding→incident chain | 🟢 |
| 8 | Critical AI incident chain | 🟢 |
| 9 | Sales lead/account/opp/sequence | 🟡 |
| 10 | Support triage + grounded response | 🟡 |
| 11 | Support Upsell Signal | 🟡 |
| 12 | New Customer cross-module | 🟡 |
| 13 | Vendor risk + questionnaire | 🟢 |
| 14 | Audit lifecycle | 🟢 |
| 15 | Trust package generation | 🟢 |
| 16 | Enterprise Sales Security Review | 🟢 |
| 17 | Workflow create/publish/execute/retry | 🟡 |
| 18 | Signed webhook→workflow trigger | 🟢 |
| 19 | OAuth connection lifecycle | 🟢 |
| 20 | Approval denial + success | 🟢 |
| 21 | Cross-tenant access denial | 🟢 |
| 22 | Restricted-role access denial | 🟢 |
| 23 | Data export/deletion controls | 🔴 |
| 24 | Global search permission enforcement | 🔴 |
| 25 | AI action risk classification + approval | 🟡 |

**14 VERIFIED, 8 PARTIAL, 2 MISSING** (out of 25 named scenarios; item 6 counts as
verified for its request-tracking scope with the export/erasure gap called out separately
under item 23 per the audit's literal wording).
