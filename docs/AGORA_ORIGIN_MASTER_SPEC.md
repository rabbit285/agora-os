# CLAUDE CODE AUTONOMOUS MASTER BUILD PROMPT — TRUST-FIRST EDITION

## Mission

You are operating as my autonomous technical co-founder and senior delivery team. Your roles include:

- Principal Software Architect
- Staff Full-Stack Engineer
- AI/ML Engineer
- Security and Privacy Engineer
- DevOps and Platform Engineer
- Product Designer
- Data Architect
- QA and Test Automation Engineer
- Technical Writer
- EU SaaS Compliance Engineering Lead

Build the complete production-oriented SaaS platform described in the product specification included below.

The working product name is **Veyntra** unless the repository already defines another approved name.

This is a serious multi-tenant B2B SaaS product for SMEs. It is not merely a UI demonstration, landing page, disconnected set of dashboards, or thin LLM wrapper.

---

# A. NON-NEGOTIABLE EXECUTION CONTRACT

## A1. Act, Do Not Only Plan

Do not stop after creating architecture documents, plans, mockups, schemas, or task lists.

After documenting the architecture, immediately implement the product in dependency order.

For every vertical slice, deliver all applicable parts:

1. Database models and constraints
2. Alembic migration
3. Domain service
4. API route and schemas
5. Authorization and tenant checks
6. Audit logging
7. Background workflow where needed
8. Frontend pages and components
9. Loading, empty, success, and error states
10. Unit and integration tests
11. End-to-end test coverage for critical flows
12. Seed/demo data
13. Documentation
14. Status-file update

A feature is not complete when only the UI exists or only the API exists.

## A2. Work Autonomously

Make reasonable engineering decisions without asking me routine questions.

Only stop for a question when all of the following are true:

- the decision has a major irreversible product or business consequence;
- no safe default can be inferred;
- the repository and specification do not already answer it;
- continuing would likely cause significant rework or a security failure.

For ordinary choices, choose the safest production-oriented option, document the decision in an ADR, and continue.

## A3. Continue Until the Environment Stops You

Continue working through the implementation phases without waiting for further prompts.

Do not say “here is the plan” and stop.

Do not ask whether you should continue.

Do not leave placeholder buttons, fake APIs, fake connector success states, or unimplemented routes unless clearly marked as unavailable and documented.

If a tool, context, or execution limit forces you to stop:

1. Leave the repository in a runnable state.
2. Update `docs/IMPLEMENTATION_STATUS.md`.
3. Create or update `docs/RESUME_BUILD.md`.
4. Record:
   - completed work;
   - current branch and commit;
   - exact commands already run;
   - test results;
   - remaining blockers;
   - the next highest-priority implementation task;
   - exact files to edit next;
   - exact command to resume.
5. Do not claim the full product is complete unless all launch gates pass.

## A4. Repository Discipline

At the start:

1. Inspect the entire repository.
2. Detect the package managers, existing conventions, configuration, and unfinished work.
3. Preserve useful existing work.
4. Do not overwrite working code unnecessarily.
5. Initialize Git if needed.
6. Use small, coherent commits after each completed vertical slice.
7. Never commit secrets, local credentials, generated private keys, or `.env`.

Maintain:

- `docs/IMPLEMENTATION_STATUS.md`
- `docs/RESUME_BUILD.md`
- `docs/DECISIONS.md`
- `docs/KNOWN_LIMITATIONS.md`
- `docs/SECURITY_ASSUMPTIONS.md`
- `docs/RELEASE_CHECKLIST.md`

---

# B. TRUST IS A CORE PRODUCT FEATURE

A customer's concern is valid:

> “It is a good idea, but companies need to fully trust you before giving you access to all these areas. That is the hard part.”

Do not solve this by asking customers for blanket access.

The platform must be designed so customers can receive useful value **without granting full access**.

The product must implement a progressive trust model.

## B1. Progressive Access Model

Support these connection stages:

### Stage 0 — No Integration

The customer can:

- create an organization;
- complete a guided assessment;
- upload selected documents manually;
- use sample data;
- review product capabilities;
- generate a readiness report.

No external system access is required.

### Stage 1 — Read-Only Connection

Default connector mode.

The platform requests only the minimum read scopes needed for the selected use case.

Examples:

- read selected Google Drive folders rather than the whole Drive;
- read selected repositories rather than all GitHub organizations;
- read CRM account and deal metadata without write access;
- read cloud security configuration without remediation permissions;
- read support tickets without sending responses.

Every connector setup page must show:

- requested permissions;
- why each permission is needed;
- which product feature uses it;
- what data will be accessed;
- what data will be stored;
- retention period;
- whether AI processing is involved;
- how to revoke access;
- last successful access;
- audit history.

### Stage 2 — Scoped Write Access

Write access is optional and disabled by default.

It must be granted per connector capability, such as:

- create CRM note;
- create task;
- draft email;
- update ticket tag;
- create calendar event.

Do not request broad write scopes when a narrower capability is available.

### Stage 3 — Approved Automation

An automation may execute only after:

- the workflow is published;
- the connector capability is enabled;
- the organization policy allows the action;
- the user has permission;
- any required human approval is completed;
- idempotency and rollback behavior are defined.

### Stage 4 — Limited Auto-Execution

Organizations may explicitly enable auto-execution only for low-risk, reversible, bounded actions.

Examples:

- add a CRM note;
- assign a support category;
- create an internal task;
- send an internal notification.

High-risk and critical actions must never become unrestricted autonomous actions.

## B2. Least Privilege

Implement least privilege across:

- OAuth scopes;
- service accounts;
- application permissions;
- database access;
- AI retrieval;
- workflow actions;
- support-agent actions;
- administrative roles;
- internal operations.

A connector must declare granular capabilities.

Example:

```text
gmail.messages.read
gmail.drafts.create
gmail.messages.send
```

These must be separately represented and governed even if a provider groups them into broader OAuth scopes.

## B3. Read-Only First

The onboarding and sales experience must emphasize:

- begin with assessment or read-only access;
- show findings before requesting write access;
- allow selective data sources;
- let customers approve individual actions;
- allow immediate disconnection;
- support export and deletion.

The product should demonstrate value before asking for deeper permissions.

## B4. Trust Center

Build a public and customer-facing Trust Center with:

- security overview;
- privacy overview;
- subprocessors;
- data locations;
- encryption practices;
- availability information;
- vulnerability reporting process;
- compliance roadmap;
- DPA availability;
- incident communication policy;
- responsible AI principles;
- AI provider disclosures;
- retention and deletion policies;
- business continuity summary;
- downloadable approved documents;
- evidence request workflow.

Do not falsely claim certifications that have not been earned.

Represent statuses accurately:

- Planned
- In Progress
- Implemented
- Independently Assessed
- Certified

## B5. Customer Data Control

Provide organization administrators with:

- connected-source inventory;
- data-source enable/disable controls;
- folder/repository/project-level scoping where providers support it;
- classification rules;
- retention settings;
- export;
- deletion;
- connector revocation;
- AI processing controls;
- model/provider selection where supported;
- region preference architecture;
- audit log access;
- organization memory review and correction;
- ability to exclude documents or fields from AI.

## B6. Explainable AI Access

For every Copilot response, show:

- sources used;
- exact records/documents accessed;
- timestamps;
- confidence;
- facts versus inference;
- proposed actions;
- permissions required;
- whether external data was used;
- whether an action was executed.

The AI must not silently search everything available.

## B7. Human Approval

Create organization-configurable action policies:

- Allowed automatically
- Allowed with approval
- Draft only
- Forbidden

Classify every action as:

- Read Only
- Low Risk
- Moderate Risk
- High Risk
- Critical

Examples:

- Summarize an authorized document: Read Only
- Draft an email: Low Risk
- Send an external email: Moderate Risk
- Change cloud access control: High Risk
- Delete regulated customer data: Critical

High-risk and critical actions require explicit approval and strong re-authentication where appropriate.

## B8. Auditability

Create immutable, append-only audit events for security-sensitive activity.

Log at minimum:

- actor;
- organization;
- legal entity where applicable;
- action;
- object;
- source IP and user agent where appropriate;
- before/after summary;
- permission decision;
- policy decision;
- AI model and prompt version;
- records and documents accessed;
- approval;
- connector call;
- result;
- timestamp;
- correlation ID.

Protect logs from tenant administrators altering historical events.

## B9. Data Protection Defaults

Default behavior:

- do not train models on customer data;
- minimize prompts;
- redact secrets and unnecessary PII;
- do not place secrets in AI prompts;
- do not log raw sensitive payloads by default;
- encrypt data in transit and at rest;
- isolate tenant data;
- use signed and expiring file URLs;
- enforce retention;
- support deletion workflows;
- preserve legal-hold architecture;
- maintain data-processing provenance.

## B10. Trust Roadmap

Implement the product so it can progressively support:

- GDPR readiness;
- EU AI Act governance;
- ISO 27001 control mapping;
- ISO 42001 control mapping;
- SOC 2 readiness;
- DPA and subprocessor management;
- SSO/SAML;
- SCIM;
- regional deployment;
- customer-managed keys;
- bring-your-own-model-key;
- private model endpoints;
- penetration testing;
- vulnerability disclosure;
- disaster recovery testing.

Do not claim that architecture alone equals legal compliance or certification.

---

# C. SECRETS AND `.env` CONTRACT

I will add real API keys later through environment variables.

Do not ask me to paste secrets into chat, source code, test fixtures, documentation, logs, or commits.

## C1. Required Files

Create:

- `.env.example`
- `.env.test.example`
- `docs/ENVIRONMENT_VARIABLES.md`
- a typed environment validation module for web, API, and worker;
- startup diagnostics that report missing variable names without exposing values.

Ensure `.env`, `.env.local`, `.env.*.local`, credentials, and private keys are ignored by Git.

## C2. Missing-Key Behavior

The application must boot locally without paid third-party API keys.

When a provider is not configured:

- mark the integration as `Not configured`;
- show a clear setup path;
- disable only the dependent capability;
- do not crash unrelated modules;
- use deterministic local adapters or clearly labeled demo adapters where useful;
- never present demo output as live provider output;
- keep interfaces identical so real adapters can be enabled later.

## C3. Environment Categories

Define and document variables for at least:

### Core

- `APP_ENV`
- `APP_URL`
- `API_URL`
- `SECRET_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `TEMPORAL_ADDRESS`
- `TEMPORAL_NAMESPACE`
- `S3_ENDPOINT_URL`
- `S3_BUCKET`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`
- `S3_REGION`

### Authentication

- session/cookie secrets;
- OAuth callback URLs;
- optional Google and Microsoft client credentials;
- optional SAML/SSO configuration architecture.

### AI Providers

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- optional Azure OpenAI settings;
- optional Google AI settings;
- embedding and reranking provider settings;
- model IDs and routing defaults.

### Email and Notifications

- transactional email provider variables;
- SMTP fallback variables;
- Slack/Teams webhook settings where relevant.

### Billing

- Stripe secret and publishable keys;
- webhook secret;
- plan/price identifiers.

### Integrations

Document provider-specific variables without hardcoding credentials.

## C4. Secret Safety

- Never return secret values through APIs.
- Store connector credentials through a secrets abstraction.
- Encrypt stored connector tokens.
- Redact secrets in logs.
- Rotate credentials without recreating connections.
- Separate development, test, staging, and production credentials.
- Ensure frontend bundles never contain server-only variables.

---

# D. AUTONOMOUS DELIVERY STRATEGY

The specification is broad. Do not reduce scope, but implement it through a coherent modular-monolith architecture and complete vertical slices.

## D1. First Runnable Milestone

The first runnable milestone must include:

- monorepo bootstrapped;
- local Docker environment;
- PostgreSQL, Redis, MinIO, and Temporal;
- web, API, and worker services;
- authentication;
- organization creation;
- tenant context;
- RBAC;
- audit logging;
- tasks;
- approvals;
- file upload;
- AI provider registry and gateway;
- deterministic unconfigured/demo AI adapter;
- app shell;
- unified dashboard;
- initial onboarding;
- health checks;
- seed organization;
- tests;
- setup documentation.

After this milestone, continue into the domain modules.

## D2. Modular Monolith

Start as a modular monolith with strong boundaries.

Do not prematurely create microservices.

Recommended backend domains:

- core
- identity
- organizations
- authorization
- audit
- files
- knowledge
- ai
- compliance
- security
- sales
- support
- automation
- integrations
- billing
- reporting
- notifications

Use interfaces and events at domain boundaries.

## D3. Product Completeness Versus Live Integrations

A feature can be complete before a paid/live external provider is configured only when:

- the domain model is complete;
- the UI is functional;
- validation, authorization, audit, and tests exist;
- the provider interface exists;
- a deterministic local or sandbox adapter exists;
- the UI clearly labels the provider state;
- no fake live success is shown.

## D4. Prioritization

Within each phase, prioritize:

1. Security and tenant isolation
2. Shared primitives
3. Data integrity
4. Trust and permissions
5. End-to-end user workflows
6. AI grounding and citations
7. Usability
8. Performance
9. Advanced integrations
10. visual polish

---

# E. TECHNICAL DEFAULTS

Use the product specification as the source of truth. Unless the repository requires otherwise, use these defaults.

## E1. Frontend

- Next.js current stable version
- TypeScript strict mode
- React
- App Router
- Tailwind CSS
- shadcn/ui and Radix primitives
- TanStack Query
- TanStack Table
- React Hook Form
- Zod
- Recharts
- React Flow for workflow editing
- Playwright for end-to-end testing
- Vitest or Jest for unit tests

## E2. Backend

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- PostgreSQL
- pgvector
- Redis
- Temporal Python SDK
- pytest
- Ruff
- mypy or pyright

## E3. Infrastructure

- Docker Compose for local development
- S3-compatible storage
- MinIO locally
- Terraform structure for cloud deployment
- CI with lint, type checking, tests, migration checks, and secret scanning
- OpenTelemetry-compatible logging, metrics, and tracing architecture

## E4. Authentication Default

Prefer a secure first-party authentication implementation or a mature self-hostable/open-source-compatible option.

Required capabilities:

- email/password;
- invitation;
- password reset;
- email verification;
- MFA/TOTP;
- secure session cookies;
- session revocation;
- organization membership;
- optional OAuth;
- SSO/SAML architecture.

Do not couple core authorization to a single SaaS authentication vendor.

## E5. Tenant Enforcement

Never accept the tenant boundary solely from a client-supplied `organization_id`.

Resolve tenant membership server-side from the authenticated principal and selected organization context.

All tenant-scoped database access must pass through reviewed patterns.

Add automated tenant-isolation tests for every major domain.

## E6. Database and Migrations

- UUID primary keys
- UTC timestamps
- strict foreign keys
- useful unique constraints
- indexes for tenant plus query keys
- optimistic concurrency or explicit versioning where needed
- soft deletion/archival only where business rules require it
- append-only records for audit-sensitive events
- migration downgrade strategy where feasible
- no schema changes hidden in application startup

## E7. API Quality

Use `/api/v1`.

Include:

- consistent error envelope;
- request/correlation IDs;
- pagination;
- sorting;
- filtering;
- idempotency for side effects;
- OpenAPI documentation;
- rate limiting;
- input limits;
- permission failures that do not leak existence of unauthorized resources.

---

# F. AI ENGINEERING RULES

## F1. Provider Gateway

Create provider-neutral interfaces:

- `generate`
- `generate_structured`
- `stream`
- `embed`
- `rerank`

Implement provider adapters separately.

Model routing must account for:

- task;
- sensitivity;
- region;
- cost;
- latency;
- context window;
- structured-output reliability;
- customer preference;
- retention settings.

## F2. No Direct Autonomous Writes

LLMs must never write directly to the database or call arbitrary external systems.

The AI may:

- retrieve authorized context;
- generate a structured proposal;
- call approved domain tools;
- create a workflow execution plan;
- request approval.

Domain services and the workflow engine execute validated actions.

## F3. Structured Outputs

Use versioned Pydantic/Zod schemas for AI outputs.

Every AI call should record:

- task type;
- prompt template and version;
- model;
- input classification;
- output schema;
- latency;
- token/cost data when available;
- citations;
- confidence;
- policy result;
- error/fallback;
- feedback.

## F4. Retrieval and Citations

RAG responses must:

- enforce permissions before retrieval;
- preserve source provenance;
- cite source document and location;
- separate sourced facts from inference;
- refuse or qualify answers when evidence is insufficient;
- avoid presenting unsupported details as facts.

## F5. Prompt Injection Defense

Treat connected and uploaded content as untrusted data.

Implement:

- clear system/data separation;
- content sanitization;
- tool allowlists;
- connector egress controls;
- sensitive-action approvals;
- suspicious-instruction detection;
- no execution of instructions found inside retrieved documents;
- security tests for indirect prompt injection.

## F6. AI Evaluation

Create repeatable evaluation fixtures for:

- citation accuracy;
- hallucination rate;
- authorization;
- tenant leakage;
- structured-output validity;
- compliance extraction;
- security recommendations;
- lead scoring;
- outreach grounding;
- support-answer grounding;
- workflow classification;
- refusal behavior.

---

# G. CONNECTOR AND AUTOMATION SAFETY

## G1. Connector SDK

Every connector must declare:

- authentication method;
- scopes;
- capabilities;
- read/write classification;
- supported objects;
- rate limits;
- webhook support;
- sync cursor behavior;
- token refresh behavior;
- error mapping;
- data-retention behavior;
- health check.

## G2. Sync Safety

Connector synchronization must support:

- idempotency;
- incremental cursors;
- retries;
- backoff;
- rate-limit handling;
- tombstones/deletions;
- partial-failure reporting;
- checkpointing;
- replay safety;
- tenant isolation.

## G3. Workflow Safety

A workflow version becomes immutable after publication.

Changes create a new draft version.

Every run must record:

- workflow version;
- trigger;
- inputs;
- node-level status;
- retries;
- outputs;
- approvals;
- errors;
- external calls;
- completion status.

Provide dry-run/test mode.

## G4. Reversibility

For actions with side effects, define:

- idempotency key;
- preconditions;
- confirmation;
- rollback or compensating action where possible;
- audit event;
- user-visible result.

---

# H. SECURITY RELEASE BASELINE

Before declaring a production release candidate, implement and test:

- tenant isolation;
- RBAC enforcement;
- MFA;
- secure cookie/session configuration;
- CSRF protection where applicable;
- CSP;
- SSRF controls;
- webhook signature verification;
- file-type, size, and malware-scan abstraction;
- rate limiting;
- brute-force protection;
- secret redaction;
- input validation;
- output encoding;
- SQL injection prevention through ORM/query patterns;
- signed object URLs;
- encryption abstraction;
- backup and restore documentation;
- dependency scanning;
- secret scanning;
- audit events;
- account and session revocation;
- secure error handling;
- production configuration checks.

Create a threat model and abuse-case tests.

---

# I. USER EXPERIENCE REQUIREMENTS

## I1. Trust-Preserving Onboarding

The onboarding flow must offer:

1. Explore with sample organization
2. Manual assessment
3. Upload selected files
4. Connect a source read-only
5. Enable selected write capability later

Show value and findings at each stage.

## I2. Permission Preview

Before requesting connector consent, show a human-readable permission preview.

Example:

```text
Read selected HubSpot companies and deals
Purpose: build account briefs and detect stalled opportunities
Stored: company, deal, and activity metadata
Not requested: sending email, deleting data, changing CRM settings
```

## I3. AI Action Preview

Before an externally visible action, show:

- action;
- destination;
- content;
- records used;
- policy result;
- risk class;
- approval requirement;
- ability to edit or cancel.

## I4. Honest States

Use accurate states:

- Live
- Sandbox
- Demo data
- Not configured
- Permission required
- Syncing
- Degraded
- Failed
- Revoked

Never show fabricated “connected” or “completed” states.

---

# J. DEFINITION OF FULL COMPLETION

Do not call the product complete merely because all routes exist.

The build is complete only when:

1. All required screen groups in the specification have implemented routes.
2. Critical paths use real domain logic and persistence.
3. All modules share core organization, user, task, approval, document, AI, workflow, and audit primitives.
4. The application runs locally from documented commands.
5. Database migrations work from a clean database.
6. Seed data loads successfully.
7. Unit, integration, authorization, tenant, and critical E2E tests pass.
8. Lint and type checks pass.
9. No secrets are committed.
10. Missing external keys degrade gracefully.
11. Trust controls are visible and functional.
12. Cross-module scenarios work end-to-end.
13. Documentation matches implementation.
14. Known limitations are explicit.
15. Release checklist is completed honestly.

---

# K. INITIAL COMMAND SEQUENCE

Begin now.

1. Inspect the repository recursively.
2. Read all existing README, architecture, environment, package, and deployment files.
3. Run existing tests and record the baseline.
4. Create/update architecture documents.
5. Create/update the implementation status.
6. Bootstrap or repair the monorepo.
7. Create the local infrastructure.
8. Implement the Phase 1 vertical slices.
9. Run all checks.
10. Fix failures before continuing.
11. Continue through the remaining phases.
12. Keep the application runnable after every completed slice.

Use the complete product specification below as mandatory scope and domain guidance.

---


# L. AWS PRODUCTION DEPLOYMENT ARCHITECTURE

Deploy the complete platform to AWS. Do not leave AWS deployment as an architecture diagram or future recommendation.

Create working Terraform, container definitions, deployment workflows, operations documentation, smoke tests, alarms, and rollback procedures.

The default production architecture must optimize for:

- strong tenant isolation;
- EU data residency;
- secure-by-default networking;
- managed AWS services;
- low operational overhead;
- repeatable infrastructure;
- environment separation;
- horizontal scaling;
- safe deployments;
- predictable rollback;
- cost visibility;
- auditability.

Do not use EKS by default.

Use **Amazon ECS with AWS Fargate** for the initial production platform because the application is containerized and does not require Kubernetes-specific capabilities. Keep the application containers portable so an EKS migration remains possible later.

## L1. AWS Region Strategy

Use configurable regions.

Default:

- Primary production region: `eu-central-1`
- Disaster-recovery region: `eu-west-1`
- Non-production: same primary region unless cost or test requirements justify otherwise

Do not hard-code the region inside application code.

Store the region in environment-specific Terraform variables.

Document all data that may leave the selected region, including:

- AI provider requests;
- email delivery;
- error monitoring;
- analytics;
- external connectors;
- support tools;
- backup copies.

The Data Residency settings page must accurately reflect actual infrastructure and subprocessors.

## L2. AWS Account and Environment Separation

Design for AWS Organizations and separate AWS accounts.

Preferred account structure:

- Management account
- Security / Log Archive account
- Non-Production account
- Production account
- Optional Backup / Disaster Recovery account

At minimum, keep production in a separate AWS account from development and staging.

Environments:

- local
- development
- staging
- production

Requirements:

- development deploys automatically after merge to the protected default branch;
- staging uses production-like topology at reduced capacity;
- production requires a protected GitHub Environment and explicit approval;
- production credentials and data must never be available to development workflows;
- cross-account roles must use least privilege;
- human production access must use temporary credentials and audited role assumption;
- no permanent IAM user access keys for CI/CD.

## L3. Required AWS Service Architecture

Use the following default service mapping.

### Edge and DNS

- Amazon Route 53 for DNS
- AWS Certificate Manager for TLS certificates
- Amazon CloudFront for edge delivery and caching
- AWS WAF attached to CloudFront
- Application Load Balancer for application routing
- AWS Shield Standard through the supported AWS edge services

Route traffic:

- `/api/*` to the API ECS service
- application and SSR routes to the web ECS service
- static assets through CloudFront caching
- health endpoints must not expose sensitive information

Prevent direct origin bypass.

Use one of these approaches, in preference order:

1. CloudFront VPC origin to a private ALB when supported by the selected Terraform AWS provider and required features.
2. Otherwise, an internet-facing ALB that only accepts CloudFront-origin traffic using the AWS-managed CloudFront origin-facing prefix list plus a secret origin header validated at the ALB or application boundary.

Never expose ECS tasks directly to the internet.

### Compute

Create separate ECS Fargate services:

- `web`
- `api`
- `worker`
- optional `scheduler`
- optional dedicated high-memory document-processing worker
- optional dedicated AI job worker

Use separate task definitions and IAM task roles.

Do not run all processes inside one container.

Required ECS behavior:

- private subnets;
- no public task IPs;
- health checks;
- graceful shutdown;
- deployment circuit breaker;
- automatic rollback;
- CloudWatch deployment alarms;
- ECS Exec disabled in production by default or restricted through audited break-glass access;
- resource limits and reservations;
- read-only root filesystem where practical;
- non-root container user;
- Linux capability removal;
- ephemeral storage explicitly sized;
- task-definition revisions;
- service auto scaling;
- minimum two tasks for production web and API services across Availability Zones;
- worker scaling based on queue depth, Temporal metrics, or workload metrics;
- deployment events sent to EventBridge and alert channels.

Use Fargate Spot only for interruptible, retry-safe non-production or background workloads. Do not use Spot for production web/API minimum capacity.

### Container Registry

Use private Amazon ECR repositories for:

- web
- API
- worker
- migration image if separate

Requirements:

- immutable release tags;
- image vulnerability scanning;
- lifecycle policies;
- encryption;
- repository policies;
- no public repositories;
- deploy by immutable image digest, not mutable tags;
- retain enough previous releases for rollback;
- generate an SBOM for release images;
- sign release images and verify signatures before production deployment where supported by the chosen tooling.

Image naming example:

```text
<account>.dkr.ecr.<region>.amazonaws.com/agora-web:<git-sha>
<account>.dkr.ecr.<region>.amazonaws.com/agora-api:<git-sha>
<account>.dkr.ecr.<region>.amazonaws.com/agora-worker:<git-sha>
```

The task definition must ultimately reference the image digest.

### Database

Use Amazon RDS for PostgreSQL.

Requirements:

- PostgreSQL version supported by the application and `pgvector`;
- Multi-AZ in production;
- private isolated database subnets;
- no public accessibility;
- storage encryption with a customer-managed KMS key;
- TLS connections;
- automated backups;
- point-in-time recovery;
- deletion protection in production;
- final snapshot on protected destruction paths;
- performance insights or equivalent monitoring;
- slow-query logging with sensitive-value precautions;
- parameter groups managed through Terraform;
- database credentials stored in Secrets Manager;
- separate database roles for application, migrations, and read-only operational access;
- connection pooling;
- explicit maximum connection budgets per service;
- maintenance window;
- backup window;
- restore testing;
- cross-region backup strategy;
- schema migration runbook.

Use one application database initially with strong schema/domain boundaries.

Do not create independent databases for every product module without a documented operational reason.

Create separate databases or schemas for infrastructure components such as self-hosted Temporal if that deployment mode is selected.

### Cache and Ephemeral State

Use Amazon ElastiCache for Valkey or Redis-compatible workloads.

Use it for:

- caching;
- rate limiting;
- distributed locks where appropriate;
- short-lived sessions only if the authentication design requires it;
- queue coordination only when not handled by Temporal.

Requirements:

- private subnets;
- encryption in transit;
- encryption at rest;
- authentication;
- Multi-AZ/automatic failover for production node-based clusters;
- backups only when the selected workload requires durability;
- eviction policy documented;
- no use as the system of record;
- namespaced keys by environment and organization where applicable.

### Object Storage

Use private Amazon S3 buckets for:

- customer files;
- parsed document artifacts;
- report exports;
- application assets where appropriate;
- audit-log exports;
- Terraform state;
- backup artifacts;
- access logs.

Requirements:

- block all public access;
- server-side encryption with KMS;
- bucket versioning;
- lifecycle rules;
- ownership controls;
- least-privilege bucket policies;
- signed, short-lived download and upload URLs;
- malware-scanning workflow;
- object metadata for tenant, classification, and retention;
- CloudTrail data-event strategy for sensitive buckets;
- access logging where appropriate;
- separate buckets by environment and security purpose;
- no customer-controlled object keys used directly as authorization.

For highly sensitive audit exports, use a dedicated log archive bucket and evaluate S3 Object Lock governance or compliance mode.

### Secrets and Configuration

Use:

- AWS Secrets Manager for secrets, rotating credentials, OAuth client secrets, database credentials, and provider keys;
- AWS Systems Manager Parameter Store for non-secret environment configuration where appropriate;
- AWS KMS customer-managed keys for sensitive production data.

ECS task definitions must reference secret ARNs, not plaintext values.

No secret value may appear in:

- Terraform source;
- Terraform state when avoidable;
- GitHub Actions logs;
- task-definition JSON;
- Docker image layers;
- application logs;
- build arguments;
- frontend environment variables;
- committed files.

Where a value must exist in Terraform state, protect the state as highly sensitive and document the limitation.

### Email

Use Amazon SES as the default transactional email provider for AWS deployment.

Implement:

- domain verification;
- DKIM;
- SPF/DMARC documentation;
- bounce and complaint handling;
- SNS event processing;
- suppression handling;
- environment-specific sender identities;
- sandbox-state detection;
- clear failure behavior when SES production access is not configured.

Do not use SES for unrestricted cold-email automation.

Sales outreach must continue to follow product compliance, suppression, and approval rules.

### Observability

Use:

- Amazon CloudWatch Logs;
- CloudWatch Metrics;
- CloudWatch Alarms;
- CloudWatch dashboards;
- AWS Distro for OpenTelemetry or OpenTelemetry-compatible collectors;
- distributed traces;
- structured JSON logs;
- correlation IDs;
- ECS Container Insights where appropriate;
- RDS monitoring;
- ElastiCache monitoring;
- ALB and CloudFront access logs;
- WAF logs;
- EventBridge for deployment and infrastructure events;
- SNS or an approved notification target for alarms.

Required dashboards:

- executive service health;
- API latency and error rates;
- web SSR health;
- worker throughput and failures;
- AI provider latency and failures;
- Temporal workflow health;
- RDS health and connections;
- Redis health;
- connector sync health;
- security events;
- cost and usage.

Required alarms:

- elevated 5xx rate;
- p95 and p99 latency thresholds;
- unhealthy ECS tasks;
- failed ECS deployment;
- ALB unhealthy targets;
- task crash loop;
- CPU/memory saturation;
- worker backlog;
- workflow failure surge;
- RDS CPU/storage/connections/replica lag;
- database failover event;
- ElastiCache memory/eviction/failover;
- WAF blocked-request anomaly;
- CloudFront origin errors;
- failed backups;
- certificate expiry;
- secret rotation failure;
- budget threshold;
- unexpected AI-cost increase.

Every alarm must include:

- severity;
- owner;
- runbook link;
- customer impact;
- first diagnostic action.

### Security Services

Enable and configure according to environment and cost profile:

- AWS CloudTrail organization or account trails;
- AWS Config;
- Amazon GuardDuty;
- AWS Security Hub;
- Amazon Inspector for supported workloads and container images;
- IAM Access Analyzer;
- AWS WAF;
- AWS KMS;
- AWS Secrets Manager;
- AWS Backup;
- Amazon Macie for selected sensitive S3 buckets where justified;
- AWS Budgets and Cost Anomaly Detection.

Do not mark the platform compliant merely because these services are enabled.

### Backups and Disaster Recovery

Use AWS Backup and native service backup features.

Production requirements:

- RDS automated backups and point-in-time recovery;
- scheduled RDS snapshots;
- S3 versioning and backup policy for critical buckets;
- cross-region backup copies;
- optional cross-account copies to a backup account;
- KMS key strategy for copied backups;
- documented restore procedure;
- quarterly restore tests;
- audit evidence for restore tests;
- application configuration export;
- Terraform state recovery process;
- incident communication process.

Set and document initial recovery objectives.

Default initial targets unless product requirements specify stricter values:

- RPO: 15 minutes for the primary transactional database
- RTO: 4 hours for regional application recovery
- lower-priority analytics and generated artifacts may have different targets

Do not claim that the targets are achieved until a recovery exercise validates them.

## L4. Network Architecture

Create a VPC spanning at least three Availability Zones in production where supported and economically reasonable.

Subnet tiers:

### Public Subnets

Only for:

- Application Load Balancer when using the public-origin fallback;
- NAT gateways.

Do not place application tasks, databases, Redis, or internal workers in public subnets.

### Private Application Subnets

For:

- ECS web tasks;
- ECS API tasks;
- ECS workers;
- migration tasks;
- internal services.

### Isolated Data Subnets

For:

- RDS;
- ElastiCache;
- self-hosted Temporal persistence if used.

Security-group rules must reference security groups, not broad CIDR ranges, wherever possible.

Default flow:

```text
Internet
  -> Route 53
  -> CloudFront
  -> AWS WAF
  -> ALB
  -> ECS web/API
  -> RDS / ElastiCache / S3 / external providers
```

Worker flow:

```text
Temporal
  -> ECS worker
  -> domain APIs / RDS / S3 / approved integrations
```

Create VPC endpoints where they reduce internet exposure and are cost-justified:

- S3 gateway endpoint;
- ECR API;
- ECR Docker registry;
- CloudWatch Logs;
- Secrets Manager;
- Systems Manager;
- KMS;
- STS;
- ECS-related endpoints where required.

Production should use one NAT gateway per Availability Zone for resilience unless an explicitly documented cost profile chooses a reduced topology.

Non-production may use a single NAT gateway to reduce cost.

## L5. IAM Architecture

Create separate IAM roles for:

- GitHub Actions Terraform plan;
- GitHub Actions non-production deployment;
- GitHub Actions production deployment;
- ECS task execution;
- web task;
- API task;
- worker task;
- migration task;
- backup operations;
- security/log export;
- break-glass operations.

Use GitHub Actions OIDC federation.

Do not store long-lived AWS access keys in GitHub secrets.

Restrict OIDC trust policies by:

- GitHub organization;
- repository;
- branch or tag;
- GitHub Environment;
- audience;
- workflow where practical.

Production deployment roles must not be assumable from pull-request workflows or unprotected branches.

Task roles must only grant the exact AWS API operations required by that service.

Examples:

- web should not have database-administration permissions;
- worker should not read every secret;
- migration role can alter the schema but cannot administer unrelated infrastructure;
- API can access only the S3 prefixes and Secrets Manager resources it needs;
- document processing can access quarantined and clean object prefixes but cannot access unrelated buckets.

Create permission boundaries or organizational guardrails for high-impact roles.

## L6. KMS Key Architecture

Create customer-managed KMS keys by environment and purpose where justified:

- application data;
- RDS;
- S3 customer files;
- secrets;
- audit/log archive;
- backups;
- Terraform state.

Requirements:

- key rotation where supported;
- aliases;
- least-privilege key policies;
- no broad account-wide decrypt permissions;
- separation between production and non-production;
- deletion waiting period;
- monitoring of key disable/delete events;
- documented recovery implications.

Avoid creating unnecessary keys that add cost and management burden without improving isolation.

## L7. Temporal Deployment

Keep Temporal as the durable application workflow engine.

Default production option:

- use Temporal Cloud;
- run Temporal workers on ECS Fargate in AWS;
- use mTLS/API-key configuration through Secrets Manager;
- keep workflow payloads minimized and encrypted where appropriate;
- use payload codecs for sensitive information;
- do not place large documents inside workflow histories;
- store large artifacts in S3 and pass controlled references.

AWS-only option:

- self-host Temporal services on ECS Fargate;
- use a dedicated RDS PostgreSQL database;
- isolate Temporal persistence from application data;
- provide upgrade, backup, restore, and operational runbooks;
- deploy multiple Temporal service replicas;
- monitor task queues, history size, workflow failures, and service health.

Do not silently select self-hosting without implementing the operational requirements.

Create a configuration switch:

```text
TEMPORAL_DEPLOYMENT_MODE=cloud|self_hosted|local
```

## L8. Infrastructure as Code

Use Terraform.

Required structure:

```text
infra/
  terraform/
    bootstrap/
    modules/
      account-baseline/
      iam-oidc/
      kms/
      networking/
      vpc-endpoints/
      ecr/
      ecs-cluster/
      ecs-service/
      alb/
      cloudfront/
      waf/
      route53/
      acm/
      rds-postgres/
      elasticache/
      s3/
      secrets/
      ses/
      observability/
      security-services/
      backup/
      budgets/
    environments/
      dev/
      staging/
      prod/
  docker/
  scripts/
```

Each module must have:

- `main.tf`
- `variables.tf`
- `outputs.tf`
- validation;
- sensible defaults;
- README;
- examples where useful.

Environment roots must compose modules rather than copy full infrastructure definitions.

### Terraform State

Bootstrap a dedicated Terraform-state bucket.

Requirements:

- S3 backend;
- bucket versioning;
- KMS encryption;
- public access blocked;
- access logging;
- least-privilege state roles;
- separate state keys by environment and stack;
- state locking using the S3 backend lockfile;
- no new DynamoDB locking dependency;
- recovery documentation;
- production state separated from non-production;
- no state file committed to Git.

Commit `.terraform.lock.hcl`.

Pin Terraform and provider version ranges.

Do not run production Terraform with an unreviewed provider upgrade.

### Terraform Commands

CI must run:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
terraform plan
```

Also run:

- linting;
- IaC security scanning;
- policy checks;
- cost estimation when supported;
- drift detection on a schedule.

Terraform apply must use a saved and reviewed plan artifact for protected environments where feasible.

## L9. Deployment Profiles and Cost Controls

Create configurable deployment profiles.

### Development

- one web task;
- one API task;
- one worker;
- smallest practical RDS;
- reduced Redis capacity;
- single NAT gateway or documented endpoint-only design;
- shorter log retention;
- no cross-region backup;
- optional scheduled shutdown for nonessential resources.

### Staging

- production-like architecture;
- reduced capacity;
- representative migrations and deployment strategy;
- synthetic data only;
- production integration sandboxes;
- enough scale for load and recovery tests.

### Production

- Multi-AZ database;
- at least two web tasks;
- at least two API tasks;
- resilient NAT topology;
- encrypted backups;
- cross-region recovery;
- complete alarms;
- protected deployment;
- WAF;
- security services;
- longer log retention;
- deletion protection.

Tag every AWS resource with:

- `Application`
- `Environment`
- `Owner`
- `CostCenter`
- `ManagedBy`
- `DataClassification`
- `BackupPolicy`
- `Repository`

Create AWS Budgets and alerts.

Create cost dashboards.

Document major fixed-cost items, especially:

- NAT gateways;
- RDS;
- ElastiCache;
- CloudFront/WAF;
- CloudWatch logs;
- VPC endpoints;
- cross-region backups;
- third-party AI usage.

# M. CI/CD PIPELINE

Implement a complete CI/CD pipeline using GitHub Actions and AWS.

The pipeline must build, test, scan, package, deploy, validate, and roll back the application.

Do not create a pipeline that only pushes a Docker image.

## M1. Required Workflow Files

Create:

```text
.github/
  workflows/
    ci.yml
    security.yml
    terraform-plan.yml
    terraform-apply-dev.yml
    terraform-apply-staging.yml
    terraform-apply-prod.yml
    build-images.yml
    deploy-dev.yml
    deploy-staging.yml
    deploy-prod.yml
    database-migration.yml
    smoke-tests.yml
    scheduled-e2e.yml
    drift-detection.yml
    rollback.yml
    release.yml
```

Reusable workflows are preferred to duplicated YAML.

Create:

```text
.github/
  actions/
```

for local composite actions only when repetition justifies them.

Pin third-party GitHub Actions to immutable commit SHAs for production-sensitive workflows.

Use Dependabot or an equivalent controlled process to update action versions.

## M2. Branch and Release Strategy

Use trunk-based development or GitHub Flow.

Required behavior:

### Pull Request

Run:

- changed-file detection;
- frontend lint;
- frontend type check;
- frontend unit tests;
- production frontend build;
- backend lint;
- backend type check;
- backend unit tests;
- API integration tests;
- migration validation;
- tenant-isolation tests;
- authorization tests;
- workflow tests;
- AI structured-output tests;
- secret scanning;
- dependency scanning;
- SAST;
- IaC validation;
- Terraform plan for affected environments;
- container build without publishing;
- container vulnerability scan;
- critical Playwright tests where practical.

A pull request cannot merge when required checks fail.

### Merge to Default Branch

After all required checks pass:

1. Build all release containers once.
2. Tag with the full Git commit SHA.
3. Generate SBOMs.
4. Scan images.
5. Push to non-production ECR.
6. Record image digests.
7. Deploy the exact digests to development.
8. Run database migrations safely.
9. Wait for ECS stability.
10. Run smoke tests.
11. Run a critical E2E test subset.
12. Publish deployment status.

Do not rebuild different container contents for later environments.

### Staging Promotion

Promote the same tested image digests to staging.

Require:

- successful development deployment;
- passing smoke and E2E tests;
- protected GitHub staging Environment;
- optional human approval;
- staging Terraform up to date;
- safe migration plan;
- release notes.

Run broader integration and load tests in staging.

### Production Promotion

Production deployment is triggered by an approved semantic-version release or a manually approved workflow tied to a specific tested commit.

Require:

- staging success;
- exact image digests;
- GitHub production Environment approval;
- production change summary;
- Terraform plan approval;
- migration risk classification;
- maintenance-window check for high-risk migrations;
- backup verification;
- deployer OIDC role;
- smoke tests;
- alarm observation period;
- release record.

Never deploy an arbitrary local image or mutable `latest` tag to production.

## M3. GitHub Actions Security

Use GitHub OIDC to assume AWS IAM roles.

Workflow permissions must be minimal.

Example baseline:

```yaml
permissions:
  contents: read
  id-token: write
```

Only add permissions required by a specific job.

Production environments must have:

- required reviewers;
- restricted deployment branches/tags;
- no untrusted fork access to secrets;
- environment-specific variables;
- wait timer only if it serves an operational purpose.

Do not print:

- OIDC tokens;
- AWS credentials;
- secret values;
- database URLs;
- full Terraform state;
- decrypted environment files.

Mask sensitive values and avoid shell tracing around secrets.

## M4. CI Test Infrastructure

Use ephemeral CI services.

Provide:

- PostgreSQL with pgvector;
- Redis/Valkey;
- MinIO or S3-compatible local test storage;
- Temporal test server or approved integration-test setup;
- mail-capture service;
- deterministic AI provider;
- mocked external connectors;
- fixture organization and users.

Tests must not require production credentials.

Separate:

- unit tests;
- integration tests;
- contract tests;
- end-to-end tests;
- live-provider tests.

Live-provider tests must be opt-in and use sandbox credentials.

## M5. Frontend CI Gates

Required:

```bash
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Use the actual repository package manager.

Add:

- accessibility tests for critical pages;
- bundle-size monitoring;
- route generation checks;
- environment-variable validation;
- Playwright critical flows;
- dependency audit;
- source-map policy.

Do not expose server-only variables through the `NEXT_PUBLIC_` namespace.

## M6. Backend CI Gates

Required:

```bash
ruff check .
ruff format --check .
mypy .
pytest
alembic upgrade head
alembic check
```

Adapt commands to the repository configuration.

Add tests for:

- clean database migration;
- migration from the previous release;
- tenant isolation;
- RBAC;
- API contracts;
- idempotency;
- workflow retries;
- audit logging;
- secrets redaction;
- connector signature verification;
- prompt injection;
- AI citations;
- background-worker cancellation;
- file authorization.

## M7. Security Pipeline

Run on pull requests, main, releases, and a schedule where appropriate.

Include:

- Git secret scanning;
- dependency vulnerability scanning;
- Python dependency audit;
- Node dependency audit;
- SAST;
- IaC scanning;
- Dockerfile scanning;
- container image scanning;
- SBOM generation;
- license-policy checks;
- Terraform policy checks;
- baseline DAST against staging;
- API fuzz or schema-based security tests for selected endpoints.

Block release on:

- committed secrets;
- critical exploitable vulnerabilities without approved exception;
- failed tenant-isolation tests;
- failed authorization tests;
- unsigned or unverified release artifacts when signing is enabled;
- high-risk Terraform policy violations.

Create a documented security-exception process with:

- owner;
- rationale;
- expiry date;
- compensating control;
- approval;
- tracking issue.

## M8. Docker Build Requirements

Create production multi-stage Dockerfiles for:

- web;
- API;
- worker.

Requirements:

- pinned base-image family and controlled updates;
- minimal runtime image;
- non-root user;
- no development dependencies in runtime;
- no secrets in build layers;
- deterministic dependency installation;
- health check support;
- labels containing repository, commit, version, and build date;
- BuildKit cache;
- reproducible build where practical;
- graceful signal handling;
- immutable filesystem assumptions;
- explicit runtime command.

Build images once per commit.

Do not use environment-specific code baked into the image.

Inject runtime configuration through ECS environment variables, Parameter Store, and Secrets Manager.

## M9. Database Migration Pipeline

Database migrations require special handling.

Implement expand-and-contract migration practices.

Examples:

- add nullable column before requiring it;
- deploy code that supports old and new schemas;
- backfill asynchronously;
- switch reads/writes;
- remove old schema in a later release.

The deployment workflow must:

1. Validate migrations against a clean database.
2. Validate upgrade from the prior release schema.
3. Detect multiple Alembic heads.
4. Classify migration risk.
5. Verify backup status before high-risk production changes.
6. Run the migration as a one-off ECS task using a dedicated migration IAM role.
7. Stream migration logs.
8. Fail deployment if migration fails.
9. Record the applied revision.
10. Avoid automatic destructive downgrade.

Do not run migrations independently in every API replica at startup.

Use an advisory lock or migration lock to prevent concurrent execution.

For long backfills:

- create a resumable Temporal workflow or dedicated job;
- add progress metrics;
- throttle load;
- support pause/resume;
- do not hold a database transaction for the full backfill.

## M10. ECS Deployment Strategy

### Development

Use ECS rolling deployment with:

- deployment circuit breaker;
- automatic rollback;
- health checks;
- minimum healthy capacity;
- smoke tests.

### Staging and Production Web/API

Implement blue/green deployment when the infrastructure and service configuration support it cleanly.

Use:

- two target groups;
- test listener;
- production listener;
- CodeDeploy or supported ECS deployment controller;
- health validation;
- smoke tests against the green target;
- controlled traffic shift;
- automatic rollback based on CloudWatch alarms.

If blue/green cannot be completed safely in the current repository, use ECS rolling deployment with:

- `minimumHealthyPercent=100`;
- `maximumPercent=200`;
- deployment circuit breaker;
- CloudWatch alarm rollback;
- explicit documentation of the limitation.

### Workers

Use rolling deployment with workflow compatibility rules.

Temporal workflow code must remain replay compatible.

Use versioning, patching, or worker build IDs where appropriate.

Do not terminate workers in a way that loses in-flight non-durable work.

## M11. Deployment Workflow Sequence

Every application deployment must follow this sequence:

```text
Resolve release commit
-> verify CI result
-> assume AWS role through OIDC
-> verify infrastructure state
-> locate immutable image digests
-> validate signatures/SBOM policy
-> verify environment configuration
-> verify recent backup
-> run pre-deployment checks
-> run safe database migration
-> register ECS task definitions
-> deploy worker compatibility version if required
-> deploy API
-> deploy web
-> wait for service stability
-> run health checks
-> run smoke tests
-> run critical E2E tests
-> observe alarms
-> publish release metadata
-> notify success or rollback
```

If a required step fails, stop.

Do not continue to production traffic shift after failed migrations or smoke tests.

## M12. Smoke Tests

Create `scripts/smoke-test.sh` or an equivalent typed script.

Test:

- public web health;
- API health;
- database connectivity through a safe endpoint;
- Redis connectivity;
- S3 signed URL generation;
- authentication route;
- organization context;
- one authorized API query;
- one unauthorized API denial;
- task/approval read;
- deterministic AI adapter or configured provider health;
- worker heartbeat;
- Temporal task queue;
- version endpoint;
- migration revision.

The health endpoint must not expose credentials, internal hostnames, stack traces, or sensitive configuration.

## M13. Production Verification

After deployment:

- verify CloudFront;
- verify WAF;
- verify ALB target health;
- verify ECS steady state;
- verify error-rate alarms;
- verify p95 latency;
- verify migration revision;
- verify one background workflow;
- verify log and trace correlation;
- verify no unexpected permission errors;
- verify audit events;
- verify release version shown in UI/API;
- verify no direct origin access.

Use synthetic test data.

Do not modify real customer records during smoke tests.

## M14. Rollback

Create a manual and automatically callable rollback workflow.

Application rollback must:

- select a previously successful release;
- use stored image digests;
- restore previous ECS task definitions;
- shift traffic back;
- wait for stability;
- run smoke tests;
- record the rollback;
- notify operators.

Database rollback policy:

- do not automatically run destructive Alembic downgrade;
- prefer forward fixes;
- rely on expand-and-contract compatibility;
- restore from backup only through an incident decision and runbook;
- document any migration that makes application rollback impossible.

Use feature flags to disable newly deployed functionality without requiring an immediate redeploy.

## M15. Infrastructure Deployment Pipeline

Terraform changes must be handled separately from application deployment.

Pull request:

```text
fmt
-> validate
-> lint
-> security scan
-> plan
-> policy check
-> cost estimate
-> publish plan summary
```

Apply:

```text
approved plan
-> protected environment
-> OIDC role
-> apply
-> verify outputs
-> infrastructure smoke checks
-> record change
```

Production Terraform apply requires approval.

Do not combine a broad infrastructure replacement with an unrelated application release.

Destructive Terraform changes must be visible in the plan summary and require explicit approval.

Prevent accidental deletion of:

- production RDS;
- production S3 customer-file buckets;
- KMS keys;
- Terraform state;
- audit logs;
- backup vaults;
- Route 53 hosted zones.

Use lifecycle protection and service deletion protection where appropriate.

## M16. Drift Detection

Create a scheduled workflow that:

- initializes Terraform read-only;
- runs `terraform plan -detailed-exitcode`;
- reports drift;
- creates an issue or notification;
- does not automatically apply unexpected production drift.

Treat manual console changes as exceptions.

## M17. Release Metadata

Store release metadata:

- semantic version;
- Git commit;
- build workflow;
- image digests;
- SBOM locations;
- migration revision;
- Terraform commit;
- deployment time;
- approver;
- environment;
- smoke-test result;
- rollback target.

Expose a safe version endpoint and a Settings/About view.

Do not expose internal account IDs or secret resource names publicly.

## M18. CI/CD Documentation

Create:

- `docs/AWS_ARCHITECTURE.md`
- `docs/AWS_ACCOUNT_STRATEGY.md`
- `docs/AWS_NETWORKING.md`
- `docs/AWS_SECURITY_BASELINE.md`
- `docs/AWS_DATA_RESIDENCY.md`
- `docs/AWS_COST_MODEL.md`
- `docs/CI_CD_PIPELINE.md`
- `docs/DEPLOYMENT_RUNBOOK.md`
- `docs/ROLLBACK_RUNBOOK.md`
- `docs/DATABASE_MIGRATION_RUNBOOK.md`
- `docs/DISASTER_RECOVERY.md`
- `docs/BACKUP_RESTORE_RUNBOOK.md`
- `docs/INCIDENT_RESPONSE_RUNBOOK.md`
- `docs/PRODUCTION_READINESS_CHECKLIST.md`

Add Mermaid diagrams for:

- AWS account structure;
- network architecture;
- request flow;
- deployment flow;
- CI/CD promotion flow;
- backup and recovery flow;
- secret flow;
- observability flow.

## M19. Required Deployment Scripts

Create safe scripts or typed CLI commands:

```text
scripts/
  bootstrap-terraform-state
  terraform-plan
  terraform-apply
  build-images
  push-images
  render-task-definition
  run-migrations
  deploy-service
  wait-for-stability
  smoke-test
  verify-release
  rollback-release
  backup-status
  restore-test
  rotate-secret
```

Requirements:

- strict shell mode if shell is used;
- clear error messages;
- environment validation;
- no secret echoing;
- dry-run where meaningful;
- confirmation for destructive operations;
- machine-readable output for CI;
- documentation.

## M20. Production Readiness Gate

Claude must not claim AWS deployment is complete until all of these pass:

- Terraform creates the environment from a clean AWS account baseline or documented prerequisites.
- GitHub OIDC role assumption works.
- No long-lived AWS key is required.
- ECR repositories exist and are protected.
- Images build and pass scans.
- RDS is private, encrypted, and backed up.
- Redis is private and encrypted.
- S3 buckets are private and encrypted.
- ECS tasks run in private subnets.
- CloudFront, WAF, TLS, and routing work.
- Secrets are loaded from Secrets Manager.
- Database migration ECS task works.
- Application deployment succeeds.
- Failed deployment rollback is tested.
- Smoke tests pass.
- Critical E2E tests pass.
- Logs, metrics, traces, and alarms work.
- Backup restore is tested.
- Production access is protected.
- Cost alerts are enabled.
- Documentation matches deployed resources.

# N. AWS IMPLEMENTATION ORDER

After completing the local Phase 1 platform foundation, implement AWS delivery in this order:

## N1. Containerization

- production Dockerfiles;
- local Compose compatibility;
- health checks;
- build scripts;
- image tests.

## N2. Terraform Bootstrap

- state bucket;
- KMS;
- OIDC identity provider;
- plan and deployment IAM roles;
- provider locking.

## N3. Network and Security Baseline

- VPC;
- subnets;
- route tables;
- NAT;
- VPC endpoints;
- security groups;
- CloudTrail;
- baseline security services.

## N4. Data Services

- RDS;
- pgvector;
- ElastiCache;
- S3;
- Secrets Manager;
- backup vaults.

## N5. Compute and Edge

- ECR;
- ECS cluster;
- task definitions;
- ECS services;
- ALB;
- CloudFront;
- WAF;
- ACM;
- Route 53.

## N6. Observability

- log groups;
- dashboards;
- alarms;
- tracing;
- deployment notifications;
- runbooks.

## N7. CI

- test workflows;
- security workflows;
- Terraform plans;
- image builds.

## N8. CD

- development deployment;
- migration job;
- smoke tests;
- staging promotion;
- production protection;
- rollback.

## N9. Recovery Validation

- backup creation;
- database restore test;
- object restore test;
- infrastructure recreation test;
- recovery documentation.

## N10. Final Verification

Deploy a seeded non-production environment and prove these flows:

1. Sign in.
2. Create organization.
3. Upload document.
4. Run AI analysis using configured or deterministic provider.
5. Create task.
6. Request approval.
7. Execute workflow.
8. View audit event.
9. Trigger background worker.
10. Deploy a new application revision.
11. Run migration.
12. Verify smoke tests.
13. Force a failed deployment in a safe test.
14. Prove automatic rollback.
15. Restore test data from backup.

Record evidence in:

- `docs/DEPLOYMENT_EVIDENCE.md`
- `docs/RECOVERY_TEST_RESULTS.md`
- `docs/PRODUCTION_READINESS_CHECKLIST.md`


# COMPLETE PRODUCT SPECIFICATION

# MASTER BUILD PROMPT

# AI-POWERED BUSINESS OPERATING SYSTEM FOR SMEs

You are my Principal Software Architect, Staff Full-Stack Engineer, AI Engineer, Security Engineer, DevOps Engineer, Product Designer, Data Architect, and technical co-founder.

Your task is to design and build a complete, production-grade SaaS platform:

# AI Business Operating System for Companies

The long-term goal is to create an AI-powered operating layer for SMEs that combines:

1. AI Compliance
2. AI Security Assistant
3. AI Sales Assistant
4. AI Customer Support Automation
5. Business Process Automation
6. Shared AI Copilot
7. Shared organization knowledge graph
8. Shared workflow and automation engine
9. Shared security, permissions, audit, and governance layer

This is NOT:

* an MVP
* a prototype
* a landing page
* a demo
* a collection of disconnected AI tools
* a simple ChatGPT wrapper

This must be architected as a serious multi-tenant B2B SaaS platform that can become the daily AI operating system used by small and mid-sized companies.

The platform should help a company:

* understand and manage regulatory obligations
* manage GDPR and AI governance
* improve security posture
* monitor security risks
* find and qualify sales prospects
* generate personalized outreach
* automate customer service
* automate internal workflows
* connect business systems
* use company knowledge safely through AI
* automate repetitive operations
* maintain auditability and human oversight
* govern all AI actions centrally

The platform's long-term positioning is:

> One secure AI operating system that helps businesses stay compliant, sell more, support customers, automate operations, and safely adopt AI.

The compliance and governance layer should sit underneath all AI modules.

Every AI action must respect:

* permissions
* data classification
* privacy rules
* security policies
* organization boundaries
* approval workflows
* audit logging
* regulatory constraints

---

# 1. CORE PRODUCT PRINCIPLE

The product should not feel like five unrelated products.

It should operate as one unified platform.

Core model:

Organization Data

↓

Unified Knowledge Layer

↓

AI Intelligence Layer

↓

Compliance + Security Governance

↓

Business Applications

* Compliance
* Security
* Sales
* Customer Support
* Process Automation

↓

Human Approval + Workflows

↓

Business Outcomes

The core flywheel is:

Company Knowledge

→ AI Understanding

→ Recommendations

→ Automated Actions

→ Human Review

→ Outcomes

→ New Knowledge

→ Better AI

---

# 2. PRIMARY PRODUCT MODULES

Build the platform around these major modules.

## Module 1 — AI Compliance

Capabilities:

* GDPR compliance
* EU AI Act
* ISO 27001
* ISO 42001
* SOC 2
* NIS2
* DORA
* custom frameworks
* control management
* evidence management
* AI governance
* privacy operations
* RoPA
* DPIAs
* DSARs
* policy management
* risk management
* vendor risk
* security questionnaires
* audits
* trust center
* regulatory intelligence
* continuous compliance monitoring
* audit readiness
* policy generation
* compliance AI Copilot

---

## Module 2 — AI Security Assistant

Capabilities:

* security posture dashboard
* asset inventory
* cloud security insights
* identity security
* vulnerability management
* security configuration monitoring
* threat alerts
* security event triage
* incident response assistance
* security questionnaire support
* policy enforcement
* security recommendations
* access review
* MFA monitoring
* risky login detection
* cloud configuration checks
* GitHub/GitLab security checks
* secret exposure detection architecture
* vendor security risk
* employee security awareness
* phishing reporting workflow
* incident playbooks
* AI-generated remediation recommendations
* security Copilot

The Security Assistant must NOT pretend to replace professional security teams.

It should:

* detect
* prioritize
* explain
* recommend
* automate low-risk remediation where approved
* escalate high-impact security actions

---

## Module 3 — AI Sales Assistant

Capabilities:

* ideal customer profile definition
* lead discovery
* lead enrichment
* account research
* contact discovery architecture
* buying signal detection
* company scoring
* lead scoring
* prospect qualification
* personalized email generation
* LinkedIn outreach drafting
* multi-step outreach sequences
* campaign generation
* sales playbooks
* lead routing
* follow-up automation
* CRM synchronization
* meeting-booking workflows
* sales pipeline intelligence
* opportunity summaries
* sales forecasting support
* objection handling
* proposal drafting
* account briefs
* meeting preparation
* call notes
* follow-up generation
* sales analytics
* AI Sales Copilot

The system must respect:

* GDPR
* ePrivacy considerations
* consent
* opt-out rules
* suppression lists
* country-specific marketing rules
* contact data provenance
* organization outreach policies

Compliance must govern sales automation.

---

## Module 4 — AI Customer Support Automation

Capabilities:

* AI support chatbot
* website chat
* email support automation
* ticket triage
* intent detection
* sentiment detection
* priority classification
* knowledge retrieval
* suggested responses
* automated responses for approved categories
* human escalation
* SLA monitoring
* multilingual support
* conversation summaries
* agent assist
* customer history
* issue classification
* refund/escalation routing
* feedback collection
* CSAT tracking
* support analytics
* knowledge-gap detection
* FAQ generation
* support content improvement
* quality assurance
* AI Support Copilot

Support AI must clearly know when to escalate to a human.

Never allow the AI to autonomously make high-risk commitments such as:

* legal promises
* major refunds
* contract changes
* account termination
* regulatory responses

unless a defined workflow explicitly authorizes it.

---

## Module 5 — Business Process Automation

This should be a general no-code / low-code AI automation platform.

Capabilities:

* workflow builder
* triggers
* conditions
* actions
* approvals
* AI steps
* data transformations
* scheduled workflows
* event workflows
* webhooks
* human tasks
* document processing
* email automation
* CRM automation
* finance workflows
* HR workflows
* onboarding workflows
* vendor onboarding
* compliance workflows
* sales workflows
* support workflows
* internal approvals
* AI document extraction
* AI classification
* AI decision support
* AI summarization
* AI generation
* RAG-based steps
* notifications
* branching
* retries
* failure handling
* workflow logs
* workflow versioning
* templates

Examples:

New vendor added

→ collect vendor information

→ send security questionnaire

→ analyze documents

→ run vendor-risk assessment

→ request DPO approval

→ create remediation tasks

→ approve vendor

Another:

New inbound lead

→ enrich company

→ calculate ICP score

→ research prospect

→ generate personalized outreach

→ human approval if needed

→ send through configured provider

→ update CRM

→ schedule follow-up

Another:

Support ticket received

→ classify

→ detect sentiment

→ search knowledge base

→ generate response

→ if confidence > threshold and category approved

→ send automatically

otherwise

→ assign human agent

---

# 3. SHARED PLATFORM SERVICES

All modules must use shared core services.

Do NOT create separate isolated architectures.

Shared services:

* Authentication
* Organizations
* Legal Entities
* Users
* Teams
* RBAC
* Permissions
* Billing
* Notifications
* Tasks
* Approvals
* Workflow Engine
* Automation Engine
* AI Model Gateway
* Knowledge Base
* Document Intelligence
* Search
* Audit Logs
* Integrations
* Secrets
* Webhooks
* API Keys
* Reporting
* Analytics
* File Storage
* Data Classification
* Governance
* Compliance Policies
* Activity History
* Observability

---

# 4. TARGET CUSTOMERS

Primary:

SMEs

Initial focus:

* SaaS companies
* AI companies
* software companies
* consulting firms
* professional services
* e-commerce
* B2B service businesses
* real estate companies
* FinTech
* HealthTech

Typical size:

10–500 employees

Core buyer personas:

* Founder
* CEO
* COO
* CTO
* CISO
* DPO
* Compliance Manager
* Head of Sales
* Head of Support
* Operations Manager
* IT Manager

---

# 5. PRODUCT POSITIONING

Possible positioning:

> AI-powered operating system for SMEs.

Alternative:

> Run compliance, security, sales, customer support, and business automation from one secure AI platform.

Core differentiator:

Most AI tools automate one department.

This platform shares:

* one company knowledge layer
* one AI infrastructure
* one governance model
* one security model
* one workflow system
* one audit trail

Across the whole business.

---

# 6. APPLICATION NAVIGATION

Design the main navigation:

Overview

AI Copilot

Compliance

* Dashboard
* Frameworks
* Controls
* Evidence
* AI Governance
* Privacy
* Risks
* Vendors
* Questionnaires
* Policies
* Audits
* Trust Center
* Regulatory Intelligence

Security

* Security Overview
* Assets
* Identity
* Cloud Security
* Vulnerabilities
* Alerts
* Incidents
* Controls
* Security Policies
* Security Training

Sales

* Sales Overview
* Leads
* Accounts
* Contacts
* Lead Finder
* Enrichment
* Sequences
* Campaigns
* Inbox
* Meetings
* Opportunities
* Pipeline
* Sales Intelligence
* Playbooks

Customer Support

* Support Overview
* Conversations
* Tickets
* AI Agent
* Knowledge Base
* Customers
* SLA
* Automations
* QA
* Analytics

Automation

* Workflows
* Templates
* Runs
* Approvals
* Connections

Knowledge

* Documents
* Knowledge Bases
* Data Sources

Tasks

Reports

Integrations

Settings

---

# 7. MAIN DASHBOARD

Create a unified executive operating dashboard.

Top-level metrics:

Compliance Health

Security Posture

Sales Pipeline

New Leads

Support SLA

Automation Hours Saved

Open Risks

Critical Alerts

AI Actions Awaiting Approval

Examples:

Compliance Health
82%

Security Score
76%

Sales Pipeline
€1.24M

Qualified Leads
142

Support SLA
94%

Automation Time Saved
318h

Critical Risks
6

Pending Approvals
14

Dashboard sections:

1. AI Daily Briefing
2. Priority Actions
3. Compliance
4. Security
5. Sales
6. Customer Support
7. Automation Performance
8. Business Activity
9. Regulatory Updates
10. AI Recommendations

AI Daily Briefing example:

Good morning.

Today you should focus on:

1. Two critical security alerts.
2. Three high-value sales opportunities need follow-up.
3. One DSAR is due within six days.
4. Customer support response time increased by 18%.
5. Four workflows failed overnight.

Buttons:

Review Critical Items

Ask AI Copilot

---

# 8. UNIFIED AI COPILOT

The global AI Copilot is central.

It must understand the user's permissions and all authorized company context.

Example requests:

Compliance:

What are our biggest GDPR gaps?

Which AI systems may fall under high-risk obligations?

Prepare a compliance remediation plan.

Security:

What security risks require attention today?

Why did our security score drop?

Show administrators without MFA.

Sales:

Find high-priority leads for our SaaS product.

Prepare an account brief for this prospect.

Write a personalized follow-up.

Support:

What are customers complaining about this week?

Draft a response to this ticket.

Show recurring issues.

Operations:

Which workflows failed?

Automate our vendor onboarding process.

Create an employee onboarding workflow.

Cross-functional:

A new enterprise prospect wants our security and compliance documents. Prepare everything needed.

The Copilot could:

1. identify the account
2. find the security questionnaire
3. find approved answers
4. retrieve compliance evidence
5. prepare a trust package
6. create sales follow-up
7. assign missing evidence tasks

That cross-module capability is a key differentiator.

---

# 9. AI COPILOT ARCHITECTURE

Architecture:

User

↓

Intent Router

↓

Authorization Engine

↓

Context Builder

↓

Relevant Domain Services

Compliance
Security
Sales
Support
Automation

↓

Knowledge Retrieval

↓

Tool Execution Planning

↓

AI Response

↓

Citations

↓

Proposed Actions

↓

Human Approval if Required

↓

Execution

Every response should separate:

Facts

Analysis

Recommendations

Actions

Sources

AI must never bypass permissions.

---

# 10. ORGANIZATION KNOWLEDGE GRAPH

Build a unified business knowledge model.

Entities:

Organization

Legal Entities

Employees

Teams

Customers

Prospects

Accounts

Contacts

Deals

Products

Services

Systems

Applications

Cloud Resources

Vendors

Contracts

Policies

Documents

Processes

Workflows

AI Systems

Data Sources

Data Categories

Processing Activities

Risks

Controls

Evidence

Support Customers

Tickets

Knowledge Articles

Security Assets

Incidents

Relationships must be queryable.

Example:

Customer

→ Contract

→ Product

→ Support Tickets

→ Account Manager

→ Security Questionnaire

→ DPA

→ Sales Opportunity

This gives AI richer context.

---

# 11. UNIFIED KNOWLEDGE PLATFORM

Create a company knowledge platform supporting:

Documents

Google Drive

SharePoint

OneDrive

Notion

Confluence architecture

Slack

Microsoft Teams

Email architecture

CRM

Support tickets

Policies

Contracts

Web pages

Databases through controlled connectors

Files:

PDF

DOCX

XLSX

CSV

TXT

HTML

PPTX architecture

Knowledge ingestion:

Connect

→ sync

→ extract

→ classify

→ chunk

→ embed

→ entity extraction

→ relationship extraction

→ index

→ authorization mapping

→ searchable knowledge

All retrieval must respect permissions.

---

# 12. AI COMPLIANCE MODULE

Build all previously defined compliance functionality.

Frameworks:

GDPR

EU AI Act

ISO 27001

ISO 42001

SOC 2

NIS2

DORA

Custom Frameworks

Architecture:

Regulation

→ Requirement

→ Control

→ Evidence

→ Assessment

→ Risk

→ Task

→ Remediation

→ Continuous Monitoring

Include:

Framework Overview

GDPR Dashboard

EU AI Act Dashboard

Control Detail

Evidence Library

Evidence Detail

Regulatory Intelligence

AI System Inventory

AI Risk Assessment

Privacy Data Inventory

RoPA

DPIA

DSAR

Retention

Transfers

Risk Register

Vendor Risk

Questionnaires

Policies

Auditor Portal

Trust Center

Reports

Compliance Copilot

---

# 13. AI SECURITY ASSISTANT

Create a full security module.

Security Overview dashboard:

Security Score

Critical Alerts

High Risks

Assets

Vulnerabilities

Identity Issues

Cloud Misconfigurations

Open Incidents

Evidence Coverage

Example:

Security Score
76%

Critical Alerts
3

High Vulnerabilities
12

Admin MFA Coverage
94%

Cloud Misconfigurations
8

Assets Monitored
348

---

# 14. SECURITY ASSET INVENTORY

Model:

Assets

* cloud accounts
* servers
* containers
* endpoints
* applications
* APIs
* repositories
* SaaS systems
* databases
* domains
* users
* privileged accounts

Fields:

Name

Type

Owner

Environment

Provider

Criticality

Data classification

Internet exposure

Last observed

Security status

Related risks

Related controls

---

# 15. CLOUD SECURITY

Connect:

AWS

Azure

GCP

Checks may include:

Public storage

Encryption configuration

Logging

MFA

IAM permissions

Unused credentials

Security groups

Public databases

Backup status

Key rotation

Root account protection

Example:

AWS S3 Public Access

Expected:
Blocked

Actual:
Enabled for 2 buckets

Severity:
High

Affected resources:
customer-export
marketing-assets

Recommendation:
Restrict public access.

Actions:

Create Task

Open Cloud Console

Generate Remediation

Assign Owner

Low-risk automated remediation can be architected but must require configured approval.

---

# 16. IDENTITY SECURITY

Integrations:

Okta

Entra ID

Google Workspace

Monitor:

MFA

Privileged accounts

Dormant accounts

Suspicious sign-ins

Password policies

Access reviews

Joiner/mover/leaver status

Overprivileged users

Example:

Administrators without MFA

2 users

Severity:
Critical

---

# 17. VULNERABILITY MANAGEMENT

Support architecture for:

Vulnerability scanners

Cloud findings

GitHub security alerts

Dependency scanners

Container scanners

Manual findings

Fields:

CVE

Asset

Severity

Exploitability

Business criticality

Known exploit

Status

Owner

Due date

Fix

Risk acceptance

AI prioritization should consider:

CVSS

Exposure

Asset criticality

Exploitability

Existing controls

---

# 18. SECURITY ALERTS

Security inbox:

New

Investigating

Contained

Resolved

False Positive

AI capabilities:

summarize event

correlate related events

identify impacted systems

suggest next steps

create incident

draft communication

Never autonomously take disruptive security action without authorization.

---

# 19. INCIDENT RESPONSE

Incident workspace:

Overview

Timeline

Affected Assets

Evidence

Tasks

Communication

Root Cause

Lessons Learned

Workflow:

Detected

→ Triage

→ Investigation

→ Containment

→ Eradication

→ Recovery

→ Postmortem

Provide playbooks:

Data breach

Compromised account

Ransomware

Cloud credential leak

Phishing

Malware

Service outage

Sensitive data exposure

Integrate incidents with:

GDPR breach process

NIS2 reporting

DORA where applicable

This connection between security and compliance is critical.

---

# 20. AI SALES ASSISTANT

Create a complete sales workspace.

Sales Dashboard:

Pipeline Value

Qualified Leads

Meetings Booked

Reply Rate

Opportunities

Win Rate

AI Suggested Actions

Example:

Pipeline
€1.24M

New Qualified Leads
84

Meetings This Month
31

Positive Reply Rate
12.8%

Open Opportunities
27

---

# 21. IDEAL CUSTOMER PROFILE

Users define ICP.

Fields:

Industries

Countries

Company size

Revenue

Technologies

Business model

Funding

Growth signals

Job roles

Pain points

Exclusions

Example:

SaaS companies

20–200 employees

Selling to enterprise

Using AWS

Hiring compliance/security staff

Recently funded

AI calculates ICP score.

---

# 22. LEAD FINDER

Filters:

Country

Industry

Employee count

Revenue

Funding

Technology

Hiring

Growth

Job titles

Company keywords

CRM status

AI score

Potential intent signals

Results:

Company

ICP Score

Reason

Signals

Relevant Contact Roles

Status

Example:

Acme Analytics

ICP Score
94

Why:

80 employees

B2B SaaS

Recently raised Series A

Hiring Security Manager

Selling to enterprise

---

# 23. LEAD ENRICHMENT

Enrich:

Company information

Website

Description

Industry

Size

Locations

Technology

Funding

Leadership

Relevant contacts

Business signals

Recent events

Public information

Store provenance.

Never create unsupported factual details.

---

# 24. SALES ACCOUNT DETAIL

Tabs:

Overview

Contacts

Research

Activity

Emails

Meetings

Opportunities

Support

Compliance Requests

Account brief:

Company

Industry

Size

Products

Challenges

Signals

Recent activity

Decision makers

Potential pitch

Relevant case studies

Risks

---

# 25. OUTREACH SEQUENCES

Sequence builder:

Step 1 Email

Wait 3 days

Step 2 LinkedIn task

Wait 4 days

Step 3 Email

Wait 7 days

Step 4 Follow-up

Conditions:

If replied → stop

If meeting booked → stop

If opt-out → suppress

If bounced → stop

If high intent → notify salesperson

AI generates personalized copy using:

Account research

Contact role

ICP

Company value proposition

Approved messaging

Compliance constraints

---

# 26. SALES EMAIL SAFETY

Implement:

Suppression list

Opt-out handling

Consent metadata

Country rule configuration

Contact provenance

Frequency caps

Company policies

Human approval mode

Auto-send mode only when configured

Never create an unrestricted mass-spam engine.

---

# 27. SALES INBOX

Unified sales conversations:

Email

CRM notes

Meeting notes

Replies

AI:

Classify intent

Positive

Neutral

Not interested

Referral

Objection

Unsubscribe

Meeting request

Generate suggested response.

---

# 28. MEETING ASSISTANT

Before meeting:

Account brief

Participants

Recent emails

Open opportunities

Potential objections

Suggested agenda

Questions to ask

After meeting:

Transcript architecture

Summary

Decisions

Pain points

Budget

Timeline

Next steps

CRM update

Follow-up email

Tasks

---

# 29. PIPELINE INTELLIGENCE

Opportunities:

Stage

Value

Probability

Expected close

Decision makers

Activity

Risk

Next step

AI recommendations:

Opportunity stalled for 14 days.

Champion has not responded.

Security review is blocking procurement.

Recommend sending Trust Center package.

This is another cross-module advantage.

---

# 30. AI CUSTOMER SUPPORT MODULE

Support Dashboard:

Open Tickets

SLA At Risk

First Response Time

Resolution Time

CSAT

AI Resolution Rate

Escalations

Top Issues

---

# 31. SUPPORT INBOX

Channels architecture:

Email

Website chat

In-app chat

API

Future:

WhatsApp

SMS

Social channels

Conversation view:

Customer

Account

Plan

History

Messages

AI summary

Sentiment

Intent

Priority

SLA

Related tickets

Suggested reply

Knowledge sources

---

# 32. AI SUPPORT AGENT

AI support flow:

Customer message

↓

Intent detection

↓

Authentication context

↓

Knowledge retrieval

↓

Policy check

↓

Confidence evaluation

↓

Action eligibility

↓

Response

Possible modes:

Suggest only

Auto-reply low-risk

Auto-resolve approved intents

Escalate

Example auto-resolvable intents:

Password reset instructions

Feature explanation

Basic troubleshooting

Billing information explanation

Documentation questions

Do not automatically perform sensitive operations without configured authorization.

---

# 33. KNOWLEDGE BASE

Support:

Articles

FAQs

Product docs

Policies

Troubleshooting

Release notes

Internal notes

AI capabilities:

Generate draft article

Detect outdated article

Detect conflicting information

Find knowledge gaps

Suggest FAQ

Suggest article improvements

Track:

Views

Usage in AI responses

Helpful score

Last reviewed

Owner

---

# 34. SUPPORT QUALITY ASSURANCE

AI reviews conversations for:

Accuracy

Tone

Policy compliance

Resolution quality

Escalation quality

Customer sentiment

Required disclosures

Create QA scores.

Managers can review.

---

# 35. SUPPORT AUTOMATION

Examples:

Ticket: refund request

→ detect category

→ check refund policy

→ evaluate amount

→ if under configured threshold

→ request approval or auto-process if explicitly allowed

→ notify customer

Another:

Ticket mentions security breach

→ mark urgent

→ notify Security

→ create incident

→ notify Compliance

→ preserve evidence

This cross-module automation is important.

---

# 36. BUSINESS PROCESS AUTOMATION ENGINE

This is a major platform capability.

Create:

Workflow Builder

Workflow Templates

Workflow Runs

Approvals

Connections

Logs

---

# 37. WORKFLOW BUILDER

Visual workflow concepts:

Trigger

Action

Condition

AI Step

Human Approval

Delay

Loop

Data Transform

Webhook

Notification

Subworkflow

End

Example:

Webhook

↓

AI Classify Document

↓

If Invoice

↓

Extract Invoice Data

↓

Approval

↓

Create Accounting Record

↓

Notify Finance

---

# 38. WORKFLOW TRIGGERS

Support architecture for:

Manual

Schedule

Webhook

API

New email

New CRM lead

CRM stage change

New support ticket

New vendor

New employee

Document uploaded

Control failed

Security alert

Form submission

Database event through connectors

New regulatory update

---

# 39. WORKFLOW ACTIONS

Actions:

Create record

Update record

Send email

Send Slack/Teams message

Create task

Assign user

Generate document

Analyze document

Extract data

Classify data

Call API

Webhook

Search knowledge

Generate AI response

Run compliance assessment

Run security check

Create lead

Update CRM

Create support ticket

Approve/reject

Create report

Wait

Branch

Loop

---

# 40. AI WORKFLOW STEPS

AI actions:

Generate text

Summarize

Classify

Extract structured data

Translate

Analyze sentiment

Score

RAG query

Research internal knowledge

Draft email

Draft policy

Assess risk

Match control

Answer questionnaire

Identify sales intent

Analyze support ticket

Return structured outputs.

All AI steps must define:

Input

Output schema

Model

Prompt version

Confidence

Failure behavior

Human review threshold

---

# 41. WORKFLOW GOVERNANCE

Every workflow has:

Owner

Version

Status

Permissions

Trigger

Actions

Secrets

Error policy

Retry policy

Audit history

Published version

Draft version

Statuses:

Draft

Testing

Active

Paused

Archived

Never allow edits to silently change active workflow behavior.

Use versioning.

---

# 42. WORKFLOW APPROVALS

Approval examples:

Manager approval

Compliance approval

Security approval

Finance approval

Legal approval

Multi-step approvals

Threshold approval

Example:

AI proposes customer refund > €500

→ Finance approval required

---

# 43. AUTOMATION ANALYTICS

Metrics:

Workflow runs

Success rate

Failure rate

Time saved

Human hours saved

Estimated value

AI cost

Average duration

Top workflows

Most failures

Automation ROI

---

# 44. SHARED TASK SYSTEM

Tasks can originate from:

Compliance

Security

Sales

Support

Automation

Vendors

Audits

AI Copilot

Fields:

Title

Module

Entity

Owner

Priority

Due date

Status

Description

Checklist

Evidence

Comments

Approvals

Activity

---

# 45. APPROVAL CENTER

Central page:

Pending Approval

Module

Action

Risk

Requested by

AI-generated?

Due

Examples:

Approve AI policy

Approve vendor

Approve outreach campaign

Approve large refund

Approve AI system classification

Approve risk acceptance

Approve workflow publication

Approve security remediation

---

# 46. DOCUMENT INTELLIGENCE

Shared document engine.

Support:

PDF

DOCX

XLSX

CSV

TXT

HTML

PPTX architecture

Images/OCR architecture

Processing:

Upload

→ security checks

→ parse

→ classify

→ chunk

→ embed

→ extract entities

→ extract relationships

→ map to business context

→ store citations

Use cases:

Compliance evidence

Contracts

Security documents

Sales proposals

Questionnaires

Customer support docs

Policies

Invoices

Vendor documents

---

# 47. UNIFIED SEARCH

Global search:

Customers

Prospects

Accounts

Contacts

Deals

Tickets

Documents

Policies

Controls

Evidence

Risks

AI Systems

Vendors

Security Assets

Incidents

Workflows

Tasks

Reports

Search must be permission-aware.

---

# 48. INTEGRATIONS PLATFORM

Build connector SDK.

Categories:

CRM:

HubSpot

Salesforce

Pipedrive

Zoho architecture

Email:

Gmail

Microsoft Outlook

Marketing:

Mailchimp architecture

Customer Support:

Zendesk

Intercom

Freshdesk architecture

Cloud:

AWS

Azure

GCP

Identity:

Okta

Entra

Google Workspace

Engineering:

GitHub

GitLab

Jira

Azure DevOps

Communication:

Slack

Teams

Documents:

Google Drive

SharePoint

OneDrive

Notion

Accounting architecture:

QuickBooks

Xero

Stripe

ERP architecture

Webhook

REST API

---

# 49. CONNECTOR CONTRACT

Every connector should support where relevant:

connect()

disconnect()

test_connection()

refresh_credentials()

capabilities()

sync()

read()

write()

subscribe()

execute_action()

collect_evidence()

health()

Connections must store:

Organization

Connector

Credentials reference

Scopes

Status

Last sync

Last error

Created by

---

# 50. DATA MODEL

Create domains.

CORE

organizations

legal_entities

business_units

users

teams

memberships

roles

permissions

subscriptions

entitlements

tasks

approvals

notifications

comments

activity_logs

files

tags

custom_fields

KNOWLEDGE

documents

document_versions

document_chunks

knowledge_bases

knowledge_sources

entities

entity_relationships

embeddings

AI

ai_providers

ai_models

ai_prompts

ai_prompt_versions

ai_runs

ai_feedback

ai_actions

ai_approvals

COMPLIANCE

frameworks

framework_versions

requirements

controls

control_mappings

control_assessments

evidence

evidence_versions

risks

policies

audits

regulatory_updates

AI GOVERNANCE

ai_systems

ai_system_versions

ai_assessments

ai_incidents

ai_monitoring

PRIVACY

processing_activities

data_categories

dpias

dsars

retention_rules

data_transfers

breaches

SECURITY

security_assets

security_findings

vulnerabilities

security_alerts

security_incidents

identity_findings

cloud_findings

security_playbooks

SALES

accounts

contacts

leads

lead_scores

lead_sources

campaigns

sequences

sequence_steps

outreach_messages

sales_conversations

meetings

opportunities

pipeline_events

sales_playbooks

SUPPORT

customers

support_conversations

tickets

ticket_messages

support_intents

knowledge_articles

support_slas

support_qa_reviews

csat_responses

AUTOMATION

workflows

workflow_versions

workflow_nodes

workflow_edges

workflow_runs

workflow_steps

workflow_errors

workflow_templates

workflow_secrets

INTEGRATIONS

integration_connections

integration_syncs

webhooks

api_keys

---

# 51. TECH STACK

Frontend:

Next.js

TypeScript

React

App Router

Tailwind CSS

shadcn/ui

Radix

TanStack Query

TanStack Table

React Hook Form

Zod

Recharts where appropriate

Visual workflow editor:

Use a robust React-based node/edge library such as React Flow or equivalent.

Backend:

Python

FastAPI

Pydantic

SQLAlchemy 2

Alembic

PostgreSQL

Redis

Background orchestration:

Temporal

Vector:

pgvector initially

Storage:

S3-compatible

Local:

MinIO

---

# 52. MONOREPO

Use:

apps/

web

api

worker

packages/

ui

config

types

sdk

ai-core

automation-core

compliance-models

integration-sdk

infra/

docker

terraform

scripts

docs/

architecture

product

security

ai

compliance

automation

integrations

adrs

---

# 53. MULTI-TENANCY

All records must be organization scoped.

Support:

Organization

Legal Entity

Business Unit

Team

Future:

Parent organization

Subsidiaries

Agency/consultant multi-client mode

Never trust organization IDs from frontend.

Enforce tenant context server-side.

Tenant isolation tests are mandatory.

---

# 54. RBAC

Default roles:

Organization Admin

Executive

Operations Manager

Compliance Manager

DPO

Security Manager

AI Governance Manager

Sales Manager

Sales Representative

Support Manager

Support Agent

Automation Manager

Legal

Auditor

Employee

Read Only

Use capability permissions.

Examples:

sales.leads.view

sales.campaigns.send

security.incidents.manage

support.tickets.respond

automation.workflows.publish

compliance.controls.override

privacy.dsars.manage

ai.actions.approve

Permissions must be enforced backend-side.

---

# 55. AI ACTION GOVERNANCE

Every AI action must be classified:

Read Only

Low Risk

Moderate Risk

High Risk

Critical

Examples:

Summarize ticket:
Read Only

Draft sales email:
Low Risk

Send customer email:
Moderate Risk

Approve vendor:
High Risk

Delete customer data:
Critical

Organization policy should define:

Auto-execute

Require approval

Forbidden

by action class.

---

# 56. AI ACTION LOG

Log:

User request

AI intent

Tools called

Data accessed

Sources

Model

Output

Suggested actions

Approvals

Executed actions

Result

Error

Timestamp

This is essential for enterprise trust.

---

# 57. MODEL GATEWAY

Internal API:

generate()

generate_structured()

embed()

rerank()

stream()

Provider adapters:

OpenAI

Anthropic

Azure OpenAI

Google architecture

Local/private future

Model routing based on:

Task

Sensitivity

Cost

Latency

Region

Customer preference

Required capabilities

---

# 58. AI SAFETY AND PRIVACY

Default:

Never train on customer data.

Support:

Provider zero-retention where available

Regional endpoints

Prompt minimization

Sensitive-data classification

PII-aware logs

Redaction where appropriate

Access controls

Bring-your-own-key future

Private model endpoint future

Customer-managed encryption future

---

# 59. SECURITY

Implement:

TLS

Encryption at rest

KMS abstraction

MFA

RBAC

SSO

SAML architecture

SCIM architecture

Rate limiting

CSP

CSRF

Secure cookies

Session revocation

Input validation

Output encoding

SSRF protections

Signed file URLs

Secret management

Audit logs

Backups

Restore procedures

Disaster recovery

Tenant isolation

File validation

Malware scanning abstraction

API security

Webhook signature verification

---

# 60. DATA CLASSIFICATION

Classifications:

Public

Internal

Confidential

Restricted

AI must respect classification.

Examples of Restricted:

DSAR identity documents

Security incident evidence

Penetration test

Passwords/secrets

Highly sensitive contracts

Special-category personal data

Users without permission must not retrieve restricted content through AI.

---

# 61. WORKFLOW ENGINE ARCHITECTURE

Use Temporal for durable operations.

Do not couple workflows directly to HTTP requests.

Examples:

Long document analysis

Bulk lead enrichment

Questionnaire processing

Regulatory impact

Security scans

DSAR

Incident response

Support automation

Sales sequences

Large reports

Integration syncing

Workflow executions must support:

Retries

Timeouts

Cancellation

Idempotency

Progress

Status

Audit history

---

# 62. EVENT ARCHITECTURE

Create an internal event system.

Examples:

document.uploaded

control.failed

security.alert.created

lead.qualified

email.reply.received

support.ticket.created

support.ticket.escalated

vendor.created

workflow.failed

ai_system.created

regulatory_update.published

dsar.deadline_approaching

Events should trigger:

Notifications

Workflows

Analytics

Automation

---

# 63. ANALYTICS

Platform analytics:

Active users

AI usage

AI cost

Automation hours saved

Compliance score trends

Security score trends

Sales metrics

Support metrics

Workflow metrics

Module adoption

Integration health

Executive metrics should be separated from internal SaaS analytics.

---

# 64. BILLING

Plans architecture:

Starter

Growth

Business

Enterprise

Potential entitlements:

Users

AI usage

Documents

Storage

Frameworks

AI systems

Security connectors

Sales leads

Outreach volume

Support conversations

Automation runs

Integrations

SSO

SCIM

API

Custom frameworks

Trust Center

Advanced reporting

Data residency

Use entitlement service.

Do not hard-code plan checks across UI.

---

# 65. REPORTING

Reports:

Executive Business AI Report

Compliance Report

Security Posture Report

GDPR Report

EU AI Act Report

AI Inventory

Risk Report

Vendor Report

Sales Performance

Pipeline Report

Support Performance

Automation ROI

Audit Evidence Pack

Board Report

Export:

PDF

DOCX

XLSX

CSV

Secure link

---

# 66. NOTIFICATIONS

Channels:

In-app

Email

Slack

Teams

Webhook

Events:

Compliance gap

Security alert

Sales reply

Lead qualified

Meeting booked

Support escalation

SLA breach

Workflow failed

Approval requested

Evidence expiring

Risk changed

Regulatory update

User preferences.

---

# 67. REQUIRED PRODUCT SCREENS

Create at minimum these major screen groups.

AUTH

Login

Signup

Invitation

MFA

Forgot password

ONBOARDING

Company Setup

Business Profile

Compliance Profile

Security Setup

Sales Setup

Support Setup

Connect Integrations

Upload Knowledge

Initial AI Analysis

Executive Results

CORE

Unified Dashboard

AI Copilot

Tasks

Approval Center

Notifications

Global Search

COMPLIANCE

Framework Overview

GDPR

EU AI Act

Control Detail

Evidence Library

Evidence Detail

AI Inventory

AI System Detail

AI Assessment

Data Inventory

DPIA

DSAR

Risk Register

Vendors

Questionnaires

Policies

Audits

Trust Center

Regulatory Intelligence

SECURITY

Security Dashboard

Asset Inventory

Asset Detail

Identity Security

Cloud Security

Vulnerabilities

Alerts

Alert Detail

Incident List

Incident Workspace

Security Policies

SALES

Sales Dashboard

ICP Builder

Lead Finder

Lead Detail

Account Detail

Contact Detail

Sequences

Sequence Builder

Campaigns

Sales Inbox

Meetings

Opportunity Detail

Pipeline

Sales Intelligence

SUPPORT

Support Dashboard

Inbox

Conversation Detail

Tickets

AI Support Agent

Knowledge Base

Article Editor

Customer Detail

SLA

QA

Support Automation

Analytics

AUTOMATION

Workflow List

Workflow Builder

Workflow Detail

Workflow Run

Workflow Templates

Approval Queue

Connections

Automation Analytics

KNOWLEDGE

Documents

Document Detail

Knowledge Bases

Sources

SETTINGS

Organization

Legal Entities

Users

Teams

Roles

AI Providers

Security

Compliance

Sales

Support

Automation

Integrations

Data Residency

Billing

API

Webhooks

Audit Logs

Data Management

---

# 68. ONBOARDING EXPERIENCE

Onboarding should ask which modules the company wants.

Step 1:
Company

Step 2:
Business profile

Step 3:
Choose goals

Checkboxes:

Improve compliance

Improve security

Find more customers

Automate customer support

Automate business operations

Step 4:
Compliance profile

Step 5:
Security profile

Step 6:
Sales profile

Step 7:
Support profile

Step 8:
Connect tools

Step 9:
Upload knowledge

Step 10:
AI analysis

Output:

Your Business AI Readiness

Compliance
63%

Security
71%

Sales Automation
42%

Support Automation
58%

Process Automation
35%

Top opportunities:

1. Fix 4 compliance gaps.
2. Enable MFA for 2 administrators.
3. 84 potential high-fit sales accounts identified.
4. 37% of support questions could be automated.
5. 12 repetitive processes identified for automation.

CTA:

Open Business Command Center

---

# 69. CROSS-MODULE USE CASES

These are essential.

## Enterprise Sales Security Review

Sales opportunity reaches Security Review stage.

System automatically:

1. Detects opportunity.
2. Finds customer questionnaire.
3. AI Compliance answers regulatory questions.
4. AI Security answers security questions.
5. Retrieves approved evidence.
6. Detects missing answers.
7. Creates tasks.
8. Generates customer trust package.
9. Sales Copilot drafts follow-up.
10. Tracks deal blocker.

---

## New AI Tool Adoption

Employee requests new AI vendor.

Workflow:

Request

→ Vendor created

→ Security assessment

→ Privacy assessment

→ EU AI Act applicability

→ DPA review

→ AI risk assessment

→ Approval

→ Add to AI inventory

→ Add approved-use policy

---

## Security Incident

Security alert detects potential breach.

System:

Creates incident

↓

Security AI summarizes

↓

Finds affected assets

↓

Checks personal-data impact

↓

Compliance module assesses GDPR breach obligations

↓

Creates incident response tasks

↓

Notifies responsible team

↓

Generates draft communications

↓

Preserves evidence

---

## New Customer

Deal closes.

Workflow:

CRM deal won

↓

Create customer

↓

Create onboarding project

↓

Send welcome email

↓

Create support profile

↓

Provision internal tasks

↓

Update billing integration

↓

Assign account owner

↓

Schedule check-in

---

## Support Upsell Signal

Customer asks repeatedly about enterprise features.

AI Support detects potential expansion.

↓

Create sales signal

↓

Notify account manager

↓

Create opportunity suggestion

↓

Generate account brief

This shows the value of one connected operating layer.

---

# 70. DESIGN SYSTEM

Visual style:

Modern enterprise SaaS.

Light theme default.

Optional dark mode.

Use:

Neutral background

Dark navy text

Subtle borders

Minimal shadows

Clear spacing

Professional typography

No excessive gradients

No neon

No generic bootstrap admin feel

Status colors consistent.

Components:

AppSidebar

TopNavigation

ModuleSwitcher

PageHeader

MetricCard

AIInsightCard

StatusBadge

RiskBadge

ConfidenceBadge

DataTable

FilterBar

CommandPalette

EntityDrawer

TaskDrawer

ApprovalPanel

ActivityTimeline

DocumentViewer

EvidenceCitation

CopilotPanel

WorkflowCanvas

WorkflowNode

SalesAccountCard

SupportConversation

SecurityFindingCard

ComplianceControlCard

AutomationRunCard

---

# 71. MODULE SWITCHER

Top-level module navigation should make it easy to switch:

Business Overview

Compliance

Security

Sales

Support

Automation

Users should still feel they are inside one platform.

---

# 72. GLOBAL CREATE

Button:

* Create

Options based on permissions:

Task

Lead

Account

Campaign

Support Ticket

AI System

Risk

Vendor

Policy

DPIA

DSAR

Workflow

Document

Report

---

# 73. DATABASE PRINCIPLES

Use UUID.

UTC timestamps.

created_at

updated_at

created_by

organization_id

legal_entity_id where relevant

Strong constraints.

Foreign keys.

Indexes.

Version critical entities.

Audit critical changes.

Use archival instead of destructive delete where required.

---

# 74. API

Use:

/api/v1/

Domains:

/auth

/organizations

/users

/knowledge

/compliance

/security

/sales

/support

/automation

/ai

/integrations

/reports

/settings

Standard:

pagination

sorting

filtering

error model

request IDs

idempotency

authorization

validation

---

# 75. OBSERVABILITY

Structured logs

Metrics

Tracing

Error monitoring

AI traces

Workflow traces

Integration health

API latency

Database performance

Usage

AI costs

Correlation IDs.

---

# 76. TESTING

Unit

Integration

Database

API

Tenant isolation

Authorization

Workflow

AI structured outputs

RAG evaluation

Frontend

E2E

Security tests

Playwright flows:

Signup

Onboarding

Connect source

Upload document

Compliance assessment

Security finding

Lead creation

Sequence creation

Support ticket

Workflow execution

AI Copilot

Cross-module workflow

Tenant isolation

RBAC denial

---

# 77. AI EVALUATION

Create evaluation datasets for:

Compliance evidence extraction

Regulatory interpretation

Security recommendations

Lead scoring

Sales personalization

Support answers

Intent detection

Workflow AI steps

Copilot answers

Citation correctness

Hallucination detection

Track:

Prompt version

Model

Score

Human feedback

---

# 78. HUMAN IN THE LOOP

Every domain must define human oversight.

Examples:

Compliance:
legal/compliance approval

Security:
security approval

Sales:
outreach approval

Support:
escalation

Automation:
approval nodes

AI must not silently perform high-impact actions.

---

# 79. IMPLEMENTATION STRATEGY

This is a FULL PRODUCT.

Do not reduce it into an MVP.

However, build in dependency order.

Phase 1 — Platform Foundation

Monorepo

Auth

Multi-tenancy

RBAC

Database

Audit

Files

Tasks

Approvals

Notifications

App shell

AI gateway

Workflow foundation

Knowledge foundation

Phase 2 — Knowledge & AI Infrastructure

Documents

Parsing

RAG

Vector search

Entity extraction

Knowledge bases

AI Copilot foundation

Phase 3 — Compliance

Frameworks

Controls

Evidence

GDPR

EU AI Act

AI governance

Privacy

Risks

Vendors

Questionnaires

Policies

Audits

Trust Center

Regulatory intelligence

Phase 4 — Security

Assets

Cloud

Identity

Findings

Vulnerabilities

Alerts

Incidents

Security Copilot

Compliance integration

Phase 5 — Sales

ICP

Lead finder

Enrichment

Accounts

Contacts

Sequences

Campaigns

Inbox

Meetings

Pipeline

Sales Copilot

CRM integrations

Phase 6 — Customer Support

Inbox

Tickets

AI Agent

Knowledge Base

SLA

QA

Analytics

Support automations

Phase 7 — Business Automation

Workflow builder

Triggers

Actions

AI steps

Approvals

Templates

Runs

Analytics

Phase 8 — Cross-Module Intelligence

Shared knowledge graph

Cross-module workflows

Executive AI

Daily briefings

Business recommendations

Cross-functional Copilot

Phase 9 — Integrations

Cloud

CRM

Support

Email

Identity

Engineering

Documents

Finance

Phase 10 — Enterprise

SSO

SAML

SCIM

Regional hosting

Enterprise RBAC

API

Webhooks

Advanced audit

Multi-entity

Agency/consultant mode

---

# 80. DO NOT BUILD DISCONNECTED MODULES

Critical rule:

Do not create:

Compliance database A

Security database B

Sales database C

Support database D

Automation database E

with no shared model.

Use shared entities wherever appropriate.

For example:

Organization

User

Company Account

Customer

Vendor

Document

Task

Activity

Comment

Approval

AI Run

Workflow

should be shared platform primitives.

---

# 81. CROSS-MODULE ENTITY LINKING

Examples:

Sales Account

↔ Customer

↔ Contract

↔ Support Conversations

↔ Security Questionnaire

↔ Trust Center Request

↔ Vendor if applicable

↔ Compliance Obligations

AI System

↔ Provider

↔ Vendor

↔ Data

↔ DPIA

↔ Risk

↔ Security Finding

↔ Control

↔ Policy

These connections are essential.

---

# 82. NO FAKE FEATURES

Do not build buttons that do nothing.

Do not create fake AI results without clearly labeled seed/demo mode.

Do not pretend connectors are live if they are not.

If feature incomplete:

show appropriate state.

---

# 83. DEFINITION OF DONE

Feature requires:

Database

Migration

Domain logic

API

Permissions

Validation

Audit

Frontend

Loading

Empty

Error

Responsive

Tests

Documentation

Seed data

Observability where appropriate

---

# 84. INITIAL SEED COMPANY

Create:

Acme AI Technologies

B2B SaaS

120 employees

Modules enabled:

Compliance

Security

Sales

Support

Automation

Seed:

Compliance:

GDPR

EU AI Act

ISO 27001

Controls

Evidence

Risks

AI systems

DPIAs

DSARs

Vendors

Policies

Security:

Assets

Findings

Alerts

Incident

Sales:

50+ leads

Accounts

Contacts

Sequences

Opportunities

Support:

Customers

Tickets

Knowledge articles

Automation:

5–10 workflows

Use realistic data.

---

# 85. INITIAL DEMO SCENARIOS

Demo should support:

Scenario 1:

User asks:

What should I focus on today?

Copilot returns:

Security alert

Compliance gap

Sales opportunity

Support SLA issue

Workflow failure

Scenario 2:

Open a sales opportunity blocked by security review.

Generate trust package.

Scenario 3:

Open an AI system.

Review security/privacy/compliance status.

Scenario 4:

Open support ticket.

AI drafts evidence-grounded response.

Scenario 5:

Open workflow builder.

Create automation.

Scenario 6:

Ask:

Which processes can we automate?

AI suggests workflows based on observed activity.

---

# 86. BUSINESS PROCESS DISCOVERY

Long-term capability:

AI analyzes connected systems and finds repetitive workflows.

Example:

I noticed that every new vendor requires:

1. Email from employee.
2. Spreadsheet entry.
3. Security questionnaire.
4. Legal review.
5. Manual Slack approval.

Recommendation:

Automate vendor onboarding.

Estimated savings:

12 hours/month

Button:

Create Workflow Draft

This should become a powerful differentiator.

---

# 87. AI RECOMMENDATION ENGINE

Recommendations can come from:

Compliance gaps

Security findings

Sales signals

Support trends

Workflow inefficiencies

Business activity

Each recommendation:

Title

Business impact

Reason

Sources

Confidence

Estimated value

Suggested action

Risk

Required approval

---

# 88. AI DAILY BRIEFING

Generate daily briefing based on authorized business data.

Sections:

Urgent

Revenue

Customers

Risk

Operations

Example:

Urgent

2 high security alerts.

Revenue

3 opportunities worth €145,000 need follow-up.

Customers

Support volume increased 18%.

Risk

One DSAR is approaching deadline.

Operations

4 workflows failed.

AI suggestion

Automate your support escalation process.

Users can click any item.

---

# 89. BUSINESS AI MEMORY

Create organization memory carefully.

Store:

Approved facts

Approved answers

Policies

Business rules

Preferences

Past decisions

Workflow outcomes

Do not rely only on raw conversation history.

Create structured memory.

Track provenance.

Allow administrators to correct/delete memory.

---

# 90. BUSINESS RULES ENGINE

Organizations should configure rules.

Examples:

Refunds over €500 require Finance approval.

High-risk AI requires DPO + AI Governance approval.

Sales outreach to Germany requires specific template.

Critical vendors require annual reassessment.

Security alerts critical severity notify CISO immediately.

Business rules should be separate from prompts.

---

# 91. COMPLIANCE AS GOVERNANCE LAYER

Critical architectural principle:

Compliance must govern the other modules.

Examples:

Sales AI asks:

Can we contact this prospect?

Compliance checks:

Jurisdiction

Data source

Marketing basis

Opt-out

Suppression

Organization policy

Support AI asks:

Can we disclose this customer information?

Compliance/security checks authorization.

Automation asks:

Can workflow export personal data?

Compliance checks:

Destination

Purpose

Permissions

Classification

This makes the platform unique.

---

# 92. SECURITY AS TRUST LAYER

Security governs:

AI access

Connections

User sessions

Sensitive data

Workflow actions

Copilot actions

External sharing

Security findings should affect:

Compliance

Vendor risk

Trust Center

Sales security reviews

---

# 93. AUTOMATION AS EXECUTION LAYER

Copilot should not contain all execution logic.

Architecture:

Copilot understands request.

↓

Creates execution plan.

↓

Calls domain APIs or workflows.

↓

Workflow engine handles execution.

This preserves:

Auditability

Retries

Approvals

Permissions

Reliability

---

# 94. FRONTEND UX

Every module should share:

Navigation

Search

Copilot

Create

Tasks

Approvals

Notifications

Entity linking

Do not force users to learn five completely different interfaces.

---

# 95. FIRST TASK FOR CLAUDE

Start by inspecting repository.

If empty:

Do NOT start coding random UI pages first.

First create:

docs/PRODUCT_VISION.md

docs/PLATFORM_ARCHITECTURE.md

docs/DOMAIN_MODEL.md

docs/DATABASE_MODEL.md

docs/AI_ARCHITECTURE.md

docs/KNOWLEDGE_ARCHITECTURE.md

docs/AUTOMATION_ARCHITECTURE.md

docs/SECURITY_ARCHITECTURE.md

docs/COMPLIANCE_ARCHITECTURE.md

docs/SALES_ARCHITECTURE.md

docs/SUPPORT_ARCHITECTURE.md

docs/INTEGRATION_ARCHITECTURE.md

docs/ROUTES_AND_SCREENS.md

docs/IMPLEMENTATION_PLAN.md

docs/IMPLEMENTATION_STATUS.md

Add Mermaid diagrams.

Then create monorepo.

Then implement Phase 1.

---

# 96. IMPLEMENTATION STATUS

Maintain:

docs/IMPLEMENTATION_STATUS.md

Use:

[x] Complete

[~] In Progress

[ ] Not Started

[!] Blocked

Sections:

Platform

Knowledge

AI

Compliance

Security

Sales

Support

Automation

Integrations

Enterprise

Testing

Infrastructure

---

# 97. HOW YOU SHOULD WORK

For each vertical slice:

1. Read architecture docs.
2. Review dependencies.
3. Update model.
4. Create migration.
5. Implement backend.
6. Implement API.
7. Add permission checks.
8. Add audit.
9. Implement frontend.
10. Add states.
11. Add tests.
12. Run lint.
13. Run typecheck.
14. Run tests.
15. Fix issues.
16. Update documentation.
17. Update status.

Do not stop at a plan.

After architecture, start creating actual code.

---

# 98. CODE QUALITY

Use modular monolith initially.

Avoid premature microservices.

Create clear domain boundaries.

No business logic inside React pages.

No authorization decisions in LLM.

No direct LLM-to-database writes.

No uncontrolled autonomous agents.

No raw SQL scattered everywhere.

No giant god classes.

No copy/paste domain models.

Strong typing.

Structured AI outputs.

Explicit interfaces.

Clean errors.

Consistent patterns.

---

# 99. SUCCESS CRITERIA

The finished platform should allow a business to:

COMPLIANCE

Manage GDPR

Manage EU AI Act

Manage security frameworks

Track controls

Track evidence

Handle privacy

Manage AI governance

Run audits

SECURITY

Monitor assets

Detect security issues

Manage incidents

Improve security posture

SALES

Find leads

Research prospects

Personalize outreach

Manage sequences

Book meetings

Manage pipeline

SUPPORT

Automate support

Assist agents

Manage knowledge

Monitor SLA

Improve support quality

AUTOMATION

Build workflows

Automate repetitive processes

Connect systems

Use AI steps

Add approvals

Monitor ROI

SHARED

Use one AI Copilot

Use one knowledge layer

Use one governance system

Use one task system

Use one workflow engine

Use one audit trail

Use one integration platform

---

# 100. FINAL PRODUCT VISION

The end product should feel like:

Vanta / OneTrust

*

AI Security Assistant

*

HubSpot-style AI Sales

*

Intercom-style AI Support

*

Zapier / Make / n8n-style Automation

*

Enterprise AI Copilot

But unified around:

European compliance

AI governance

Security

Company knowledge

Business automation

The platform should become:

> The secure AI operating system for SMEs.

A company should be able to connect its tools and data, then use one intelligent platform to:

Stay compliant.

Stay secure.

Find customers.

Serve customers.

Automate operations.

Make better decisions.

All while maintaining:

Human oversight

Security

Privacy

Compliance

Explainability

Auditability

---

# 101. BEGIN NOW

Do the following immediately:

1. Inspect the repository.
2. Create the architecture documentation.
3. Define the monorepo.
4. Define domain boundaries.
5. Define shared platform primitives.
6. Define database schema.
7. Define event architecture.
8. Define AI architecture.
9. Define workflow architecture.
10. Define security architecture.
11. Define screen/route architecture.
12. Define implementation phases.
13. Create IMPLEMENTATION_STATUS.md.
14. Build Phase 1 platform foundation.

Do not merely explain what should be built.

Start creating the actual product.

When a reasonable engineering choice can be inferred, make the decision and document it.

Only ask me questions when a decision has a major product or business consequence that cannot reasonably be inferred.

Build this as a production-grade, scalable, secure, AI-native SaaS platform intended to become the operating system for SMEs.


---

# FINAL AUTONOMOUS BUILD DIRECTIVE

The specification above defines the target product.

Your immediate behavior must be:

- inspect;
- document;
- implement;
- test;
- fix;
- commit;
- continue.

Do not respond with only an explanation of how to build it.

Create the actual files and working code.

Do not request API keys during implementation. Generate `.env.example`, use safe unconfigured adapters, and keep all provider-dependent features honest until credentials are added.

Do not ask customers for full system access. Implement progressive, least-privilege, read-only-first access and make trust controls a visible part of the product.

Implement the AWS infrastructure and GitHub Actions CI/CD pipeline described above. A local-only application is not the final deliverable. Use Terraform, ECS Fargate, ECR, RDS PostgreSQL, ElastiCache, S3, CloudFront, WAF, Secrets Manager, KMS, CloudWatch, AWS Backup, and GitHub OIDC unless an existing repository constraint requires a documented alternative.

When a real integration cannot be completed without external credentials or vendor approval, complete the provider-neutral interface, local/sandbox adapter, configuration UI, permission model, tests, and setup documentation. Mark the live adapter as `Not configured`, not as complete/live.

Continue until the implementation is genuinely complete or the execution environment imposes a hard stop. If forced to stop, leave an exact, executable continuation record in `docs/RESUME_BUILD.md`.
