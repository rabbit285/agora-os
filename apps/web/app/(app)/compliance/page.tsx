"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  AIIncident,
  AIRiskClassification,
  AISystem,
  Audit,
  Control,
  DataTransfer,
  DataTransferStatus,
  DPIA,
  DPIARiskLevel,
  DSAR,
  DSARRequestType,
  Evidence,
  EvidenceRequest,
  Framework,
  LegalBasis,
  Policy,
  ProcessingActivity,
  Questionnaire,
  QuestionnaireSource,
  Risk,
  SalesOpportunity,
  SecurityReview,
  Severity,
  TransferMechanism,
  TrustCenterCategory,
  TrustCenterItem,
  TrustCenterItemStatus,
  Vendor,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm text-[var(--fg-default)] shadow-[var(--shadow-token-sm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

function ControlsSection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");

  const { data: controls } = useQuery<Control[]>({
    queryKey: ["compliance", "controls"],
    queryFn: () => apiFetch<Control[]>("/api/v1/compliance/controls"),
  });

  const createControl = useMutation({
    mutationFn: (newTitle: string) =>
      apiFetch<Control>("/api/v1/compliance/controls", { method: "POST", body: { title: newTitle } }),
    onSuccess: () => {
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "controls"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Controls
      </h2>
      <Card className="mb-4">
        <CardContent className="flex gap-2 pt-6">
          <Input
            placeholder="New control title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && title.trim()) createControl.mutate(title.trim());
            }}
          />
          <Button disabled={!title.trim() || createControl.isPending} onClick={() => createControl.mutate(title.trim())}>
            Add control
          </Button>
        </CardContent>
      </Card>
      {controls?.length === 0 && <p className="text-sm text-[var(--fg-muted)]">No controls yet.</p>}
      <div className="flex flex-col gap-2">
        {controls?.map((control) => (
          <Link key={control.id} href={`/compliance/controls/${control.id}`}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div className="font-medium text-[var(--fg-default)]">{control.title}</div>
                <StatusBadge status={control.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function RisksSection() {
  const { data: risks } = useQuery<Risk[]>({
    queryKey: ["compliance", "risks"],
    queryFn: () => apiFetch<Risk[]>("/api/v1/compliance/risks"),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Risk Register
      </h2>
      {risks?.length === 0 && <p className="text-sm text-[var(--fg-muted)]">No risks recorded.</p>}
      <div className="flex flex-col gap-2">
        {risks?.map((risk) => (
          <Card key={risk.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">{risk.title}</div>
                <div className="mt-1 flex gap-2">
                  <Badge variant="outline">likelihood: {risk.likelihood}</Badge>
                  <Badge variant="outline">impact: {risk.impact}</Badge>
                </div>
              </div>
              <StatusBadge status={risk.status} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function VendorsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");

  const { data: vendors } = useQuery<Vendor[]>({
    queryKey: ["compliance", "vendors"],
    queryFn: () => apiFetch<Vendor[]>("/api/v1/compliance/vendors"),
  });

  const createVendor = useMutation({
    mutationFn: () =>
      apiFetch<Vendor>("/api/v1/compliance/vendors", {
        method: "POST",
        body: { name, category: category.trim() || "general" },
      }),
    onSuccess: () => {
      setName("");
      setCategory("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "vendors"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Vendors
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <Input
            placeholder="Vendor name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <Input
            placeholder="Category (e.g. cloud_infrastructure)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <Button disabled={!name.trim() || createVendor.isPending} onClick={() => createVendor.mutate()}>
            Add vendor
          </Button>
        </CardContent>
      </Card>
      {vendors?.length === 0 && <p className="text-sm text-[var(--fg-muted)]">No vendors recorded yet.</p>}
      <div className="flex flex-col gap-2">
        {vendors?.map((vendor) => (
          <Link key={vendor.id} href={`/compliance/vendors/${vendor.id}`}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{vendor.name}</div>
                  <div className="text-xs text-[var(--fg-subtle)]">{vendor.category}</div>
                </div>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={vendor.risk_tier} />
                  <StatusBadge status={vendor.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function QuestionnairesSection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [source, setSource] = useState<QuestionnaireSource>("internal_template");

  const { data: questionnaires } = useQuery<Questionnaire[]>({
    queryKey: ["compliance", "questionnaires"],
    queryFn: () => apiFetch<Questionnaire[]>("/api/v1/compliance/questionnaires"),
  });

  const createQuestionnaire = useMutation({
    mutationFn: () =>
      apiFetch<Questionnaire>("/api/v1/compliance/questionnaires", {
        method: "POST",
        body: { title, source },
      }),
    onSuccess: () => {
      setTitle("");
      setSource("internal_template");
      queryClient.invalidateQueries({ queryKey: ["compliance", "questionnaires"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Questionnaires
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <Input
            placeholder="Questionnaire title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <select
            className={selectClassName}
            value={source}
            onChange={(e) => setSource(e.target.value as QuestionnaireSource)}
          >
            <option value="internal_template">Internal template</option>
            <option value="customer_provided">Customer provided</option>
          </select>
          <Button
            disabled={!title.trim() || createQuestionnaire.isPending}
            onClick={() => createQuestionnaire.mutate()}
          >
            Create questionnaire
          </Button>
        </CardContent>
      </Card>
      {questionnaires?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No questionnaires yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {questionnaires?.map((questionnaire) => (
          <Link
            key={questionnaire.id}
            href={`/compliance/questionnaires/${questionnaire.id}`}
          >
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{questionnaire.title}</div>
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {questionnaire.source.replace(/_/g, " ")}
                  </div>
                </div>
                <StatusBadge status={questionnaire.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function AuditsSection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [auditorName, setAuditorName] = useState("");

  const { data: audits } = useQuery<Audit[]>({
    queryKey: ["compliance", "audits"],
    queryFn: () => apiFetch<Audit[]>("/api/v1/compliance/audits"),
  });

  const createAudit = useMutation({
    mutationFn: () =>
      apiFetch<Audit>("/api/v1/compliance/audits", {
        method: "POST",
        body: { title, auditor_name: auditorName.trim() || null },
      }),
    onSuccess: () => {
      setTitle("");
      setAuditorName("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "audits"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Audits
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <Input
            placeholder="Audit title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <Input
            placeholder="Auditor name"
            value={auditorName}
            onChange={(e) => setAuditorName(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <Button disabled={!title.trim() || createAudit.isPending} onClick={() => createAudit.mutate()}>
            Create audit
          </Button>
        </CardContent>
      </Card>
      {audits?.length === 0 && <p className="text-sm text-[var(--fg-muted)]">No audits recorded yet.</p>}
      <div className="flex flex-col gap-2">
        {audits?.map((audit) => (
          <Link key={audit.id} href={`/compliance/audits/${audit.id}`}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{audit.title}</div>
                  <div className="text-xs text-[var(--fg-subtle)]">{audit.auditor_name ?? "No auditor set"}</div>
                </div>
                <StatusBadge status={audit.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

const TRUST_CENTER_CATEGORIES: TrustCenterCategory[] = [
  "security_overview",
  "privacy_overview",
  "subprocessors",
  "data_locations",
  "encryption_practices",
  "availability",
  "vulnerability_reporting",
  "compliance_roadmap",
  "dpa_availability",
  "incident_communication",
  "responsible_ai",
  "ai_provider_disclosures",
  "retention_deletion",
  "business_continuity",
];

/** The two statuses that assert an outside party's conclusion rather than
 * our own work. Mirrors ATTESTED_STATUSES on the API, which enforces it —
 * this only decides whether to show the attestation fields. */
const ATTESTED_STATUSES = new Set<TrustCenterItemStatus>([
  "independently_assessed",
  "certified",
]);

function TrustCenterSection() {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<TrustCenterCategory>("security_overview");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [itemStatus, setItemStatus] = useState<TrustCenterItemStatus>("planned");
  const [isPublic, setIsPublic] = useState(false);
  const [attestationFileId, setAttestationFileId] = useState("");
  const [attestationNote, setAttestationNote] = useState("");

  const { data: items } = useQuery<TrustCenterItem[]>({
    queryKey: ["compliance", "trust-center-items"],
    queryFn: () => apiFetch<TrustCenterItem[]>("/api/v1/trust-center/items"),
  });

  const { data: evidenceRequests } = useQuery<EvidenceRequest[]>({
    queryKey: ["compliance", "trust-center-evidence-requests"],
    queryFn: () => apiFetch<EvidenceRequest[]>("/api/v1/trust-center/evidence-requests"),
  });

  const saveItem = useMutation({
    mutationFn: () =>
      apiFetch<TrustCenterItem>("/api/v1/trust-center/items", {
        method: "POST",
        body: {
          category,
          title,
          content: content.trim() || null,
          status: itemStatus,
          is_public: isPublic,
          attestation_file_id: attestationFileId.trim() || null,
          attestation_note: attestationNote.trim() || null,
        },
      }),
    onSuccess: () => {
      setTitle("");
      setContent("");
      setItemStatus("planned");
      setIsPublic(false);
      setAttestationFileId("");
      setAttestationNote("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "trust-center-items"] });
    },
  });

  const fulfillRequest = useMutation({
    mutationFn: (requestId: string) =>
      apiFetch(`/api/v1/trust-center/evidence-requests/${requestId}/status`, {
        method: "PATCH",
        body: { status: "fulfilled" },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "trust-center-evidence-requests"] }),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Trust Center
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-2 pt-6">
          <div className="flex flex-wrap gap-2">
            <select
              className={selectClassName}
              value={category}
              onChange={(e) => setCategory(e.target.value as TrustCenterCategory)}
            >
              {TRUST_CENTER_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            <Input
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="min-w-[200px] flex-1"
            />
            <select
              className={selectClassName}
              value={itemStatus}
              onChange={(e) => setItemStatus(e.target.value as TrustCenterItemStatus)}
            >
              <option value="planned">Planned</option>
              <option value="in_progress">In progress</option>
              <option value="implemented">Implemented</option>
              <option value="independently_assessed">Independently assessed</option>
              <option value="certified">Certified</option>
            </select>
          </div>
          <Input
            placeholder="Content (public-facing description)"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <label className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Publish on public Trust Center page
          </label>

          {/* "Independently assessed" and "certified" state what an
              outside party concluded — the only claims on a trust page a
              buyer cannot check against the rest of it. The API refuses
              them without an attestation, so the form has to collect one
              rather than leaving the reader with a 422 and no way to
              comply. */}
          {ATTESTED_STATUSES.has(itemStatus) && (
            <div className="flex flex-col gap-2 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--warning-700)]">
                Attestation required
              </p>
              <p className="text-sm leading-relaxed text-[var(--warning-700)]">
                This status says an external party assessed your organization. It cannot be
                inferred from the controls recorded here, so attach the certificate or audit
                report and say what it covers.
              </p>
              <Input
                placeholder="Attestation document file ID"
                value={attestationFileId}
                onChange={(e) => setAttestationFileId(e.target.value)}
              />
              <Input
                placeholder="Who issued it and what it covers (e.g. scope, audit period)"
                value={attestationNote}
                onChange={(e) => setAttestationNote(e.target.value)}
              />
            </div>
          )}

          {saveItem.isError && (
            <p className="text-sm text-[var(--critical-600)]">
              {(saveItem.error as Error).message}
            </p>
          )}

          <Button
            disabled={!title.trim() || saveItem.isPending}
            onClick={() => saveItem.mutate()}
            className="w-fit"
          >
            Save item
          </Button>
        </CardContent>
      </Card>
      {items?.length === 0 && (
        <p className="mb-4 text-sm text-[var(--fg-muted)]">No Trust Center items configured yet.</p>
      )}
      <div className="mb-6 flex flex-col gap-2">
        {items?.map((item) => (
          <Card key={item.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">{item.title}</div>
                <div className="text-xs text-[var(--fg-subtle)]">{item.category.replace(/_/g, " ")}</div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={item.is_public ? "success" : "outline"}>
                  {item.is_public ? "public" : "private"}
                </Badge>
                <StatusBadge status={item.status} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Evidence Requests
      </h3>
      {evidenceRequests?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No evidence requests yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {evidenceRequests?.map((request) => (
          <Card key={request.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">
                  {request.requester_name}
                  {request.company_name ? ` (${request.company_name})` : ""}
                </div>
                <div className="text-xs text-[var(--fg-subtle)]">{request.requester_email}</div>
                {request.message && (
                  <div className="text-sm text-[var(--fg-muted)]">{request.message}</div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={request.status} />
                {request.status === "open" && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={fulfillRequest.isPending}
                    onClick={() => fulfillRequest.mutate(request.id)}
                  >
                    Mark fulfilled
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function SecurityReviewsSection() {
  const queryClient = useQueryClient();
  const [opportunityId, setOpportunityId] = useState("");
  const [importQuestionnaireId, setImportQuestionnaireId] = useState("");

  const { data: reviews } = useQuery<SecurityReview[]>({
    queryKey: ["compliance", "security-reviews"],
    queryFn: () => apiFetch<SecurityReview[]>("/api/v1/compliance/security-reviews"),
  });

  const { data: opportunities } = useQuery<SalesOpportunity[]>({
    queryKey: ["sales", "opportunities"],
    queryFn: () => apiFetch<SalesOpportunity[]>("/api/v1/sales/opportunities"),
  });

  const { data: questionnaires } = useQuery<Questionnaire[]>({
    queryKey: ["compliance", "questionnaires"],
    queryFn: () => apiFetch<Questionnaire[]>("/api/v1/compliance/questionnaires"),
  });

  const startReview = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/compliance/security-reviews", {
        method: "POST",
        body: {
          opportunity_id: opportunityId,
          questionnaire_id: importQuestionnaireId || null,
        },
      }),
    onSuccess: () => {
      setOpportunityId("");
      setImportQuestionnaireId("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "security-reviews"] });
      queryClient.invalidateQueries({ queryKey: ["sales", "opportunities"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Enterprise Sales Security Reviews
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <select
            className={selectClassName}
            value={opportunityId}
            onChange={(e) => setOpportunityId(e.target.value)}
          >
            <option value="">Select opportunity…</option>
            {opportunities?.map((o) => (
              <option key={o.id} value={o.id}>
                {o.title}
              </option>
            ))}
          </select>
          <select
            className={selectClassName}
            value={importQuestionnaireId}
            onChange={(e) => setImportQuestionnaireId(e.target.value)}
          >
            <option value="">Create new questionnaire</option>
            {questionnaires
              ?.filter((q) => !q.opportunity_id)
              .map((q) => (
                <option key={q.id} value={q.id}>
                  Import: {q.title}
                </option>
              ))}
          </select>
          <Button
            disabled={!opportunityId || startReview.isPending}
            onClick={() => startReview.mutate()}
          >
            Start review
          </Button>
        </CardContent>
      </Card>
      {reviews?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No security reviews started yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {reviews?.map((review) => (
          <Link key={review.id} href={`/compliance/security-reviews/${review.id}`}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">
                    {opportunities?.find((o) => o.id === review.opportunity_id)?.title ??
                      review.opportunity_id}
                  </div>
                  {review.is_deal_blocker && (
                    <div className="text-xs text-[var(--critical-600)]">Deal blocker</div>
                  )}
                </div>
                <StatusBadge status={review.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function AISystemsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [riskClassification, setRiskClassification] = useState<AIRiskClassification>("minimal");

  const { data: aiSystems } = useQuery<AISystem[]>({
    queryKey: ["compliance", "ai-systems"],
    queryFn: () => apiFetch<AISystem[]>("/api/v1/compliance/ai-systems"),
  });

  const registerSystem = useMutation({
    mutationFn: () =>
      apiFetch<AISystem>("/api/v1/compliance/ai-systems", {
        method: "POST",
        body: { name, purpose, risk_classification: riskClassification },
      }),
    onSuccess: () => {
      setName("");
      setPurpose("");
      setRiskClassification("minimal");
      queryClient.invalidateQueries({ queryKey: ["compliance", "ai-systems"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        AI System Inventory
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <Input
            placeholder="System name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <Input
            placeholder="Purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <select
            className={selectClassName}
            value={riskClassification}
            onChange={(e) => setRiskClassification(e.target.value as AIRiskClassification)}
          >
            <option value="minimal">Minimal risk</option>
            <option value="limited">Limited risk</option>
            <option value="high">High risk</option>
            <option value="unacceptable">Unacceptable risk</option>
          </select>
          <Button
            disabled={!name.trim() || !purpose.trim() || registerSystem.isPending}
            onClick={() => registerSystem.mutate()}
          >
            Register AI system
          </Button>
        </CardContent>
        <CardContent className="pt-0 pb-4">
          <p className="text-xs text-[var(--fg-subtle)]">
            High or unacceptable-risk systems automatically require an Approval before they can be
            marked approved (spec section 69 — New AI Tool Adoption).
          </p>
        </CardContent>
      </Card>
      {aiSystems?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No AI systems registered yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {aiSystems?.map((system) => (
          <Link key={system.id} href={`/compliance/ai-systems/${system.id}`}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{system.name}</div>
                  {system.vendor && (
                    <div className="text-xs text-[var(--fg-subtle)]">{system.vendor}</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={system.risk_classification} />
                  <StatusBadge status={system.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function AIIncidentsSection() {
  const queryClient = useQueryClient();
  const [aiSystemId, setAiSystemId] = useState("");
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState<Severity>("low");

  const { data: aiSystems } = useQuery<AISystem[]>({
    queryKey: ["compliance", "ai-systems"],
    queryFn: () => apiFetch<AISystem[]>("/api/v1/compliance/ai-systems"),
  });

  const { data: incidents } = useQuery<AIIncident[]>({
    queryKey: ["compliance", "ai-incidents"],
    queryFn: () => apiFetch<AIIncident[]>("/api/v1/compliance/ai-incidents"),
  });

  const createIncident = useMutation({
    mutationFn: () =>
      apiFetch<AIIncident>("/api/v1/compliance/ai-incidents", {
        method: "POST",
        body: { ai_system_id: aiSystemId, title, severity },
      }),
    onSuccess: () => {
      setTitle("");
      setSeverity("low");
      queryClient.invalidateQueries({ queryKey: ["compliance", "ai-incidents"] });
    },
  });

  const aiSystemNames = new Map((aiSystems ?? []).map((s) => [s.id, s.name]));

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        AI Incidents
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <select
            className={selectClassName}
            value={aiSystemId}
            onChange={(e) => setAiSystemId(e.target.value)}
          >
            <option value="">Select AI system…</option>
            {aiSystems?.map((system) => (
              <option key={system.id} value={system.id}>
                {system.name}
              </option>
            ))}
          </select>
          <Input
            placeholder="Incident title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <select
            className={selectClassName}
            value={severity}
            onChange={(e) => setSeverity(e.target.value as Severity)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
          <Button
            disabled={!aiSystemId || !title.trim() || createIncident.isPending}
            onClick={() => createIncident.mutate()}
          >
            Log incident
          </Button>
        </CardContent>
        <CardContent className="pt-0 pb-4">
          <p className="text-xs text-[var(--fg-subtle)]">
            A critical incident automatically creates a linked Risk and response Task, and
            notifies the incident owner (EU AI Act Article 73 serious-incident obligations).
          </p>
        </CardContent>
      </Card>
      {incidents?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No AI incidents logged yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {incidents?.map((incident) => (
          <Link key={incident.id} href={`/compliance/ai-incidents/${incident.id}`}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{incident.title}</div>
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {aiSystemNames.get(incident.ai_system_id) ?? "Unknown system"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={incident.severity} />
                  <StatusBadge status={incident.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

const LEGAL_BASIS_OPTIONS: { value: LegalBasis; label: string }[] = [
  { value: "consent", label: "Consent" },
  { value: "contract", label: "Contract" },
  { value: "legal_obligation", label: "Legal obligation" },
  { value: "vital_interests", label: "Vital interests" },
  { value: "public_task", label: "Public task" },
  { value: "legitimate_interests", label: "Legitimate interests" },
];

function ProcessingActivitiesSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [legalBasis, setLegalBasis] = useState<LegalBasis>("legitimate_interests");
  const [dataSubjects, setDataSubjects] = useState("");
  const [retentionPeriod, setRetentionPeriod] = useState("");

  const { data: activities } = useQuery<ProcessingActivity[]>({
    queryKey: ["compliance", "processing-activities"],
    queryFn: () => apiFetch<ProcessingActivity[]>("/api/v1/compliance/processing-activities"),
  });

  const createActivity = useMutation({
    mutationFn: () =>
      apiFetch<ProcessingActivity>("/api/v1/compliance/processing-activities", {
        method: "POST",
        body: {
          name,
          purpose,
          legal_basis: legalBasis,
          data_subjects: dataSubjects,
          retention_period: retentionPeriod,
        },
      }),
    onSuccess: () => {
      setName("");
      setPurpose("");
      setDataSubjects("");
      setRetentionPeriod("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "processing-activities"] });
    },
  });

  const canCreate =
    name.trim() && purpose.trim() && dataSubjects.trim() && retentionPeriod.trim();

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Record of Processing Activities (RoPA)
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <Input
            placeholder="Activity name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <Input
            placeholder="Purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <select
            className={selectClassName}
            value={legalBasis}
            onChange={(e) => setLegalBasis(e.target.value as LegalBasis)}
          >
            {LEGAL_BASIS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <Input
            placeholder="Data subjects (e.g. customers)"
            value={dataSubjects}
            onChange={(e) => setDataSubjects(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <Input
            placeholder="Retention period"
            value={retentionPeriod}
            onChange={(e) => setRetentionPeriod(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <Button disabled={!canCreate || createActivity.isPending} onClick={() => createActivity.mutate()}>
            Add activity
          </Button>
        </CardContent>
      </Card>
      {activities?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No processing activities recorded yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {activities?.map((activity) => (
          <Card key={activity.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">{activity.name}</div>
                <div className="text-xs text-[var(--fg-subtle)]">
                  {activity.legal_basis.replace(/_/g, " ")} · {activity.data_subjects}
                </div>
              </div>
              <StatusBadge status={activity.status} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function DPIASection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [riskLevel, setRiskLevel] = useState<DPIARiskLevel>("low");

  const { data: dpias } = useQuery<DPIA[]>({
    queryKey: ["compliance", "dpias"],
    queryFn: () => apiFetch<DPIA[]>("/api/v1/compliance/dpias"),
  });

  const createDpia = useMutation({
    mutationFn: () =>
      apiFetch<DPIA>("/api/v1/compliance/dpias", {
        method: "POST",
        body: { title, risk_level: riskLevel },
      }),
    onSuccess: () => {
      setTitle("");
      setRiskLevel("low");
      queryClient.invalidateQueries({ queryKey: ["compliance", "dpias"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Data Protection Impact Assessments (DPIA)
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <Input
            placeholder="DPIA title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <select
            className={selectClassName}
            value={riskLevel}
            onChange={(e) => setRiskLevel(e.target.value as DPIARiskLevel)}
          >
            <option value="low">Low risk</option>
            <option value="medium">Medium risk</option>
            <option value="high">High risk</option>
          </select>
          <Button disabled={!title.trim() || createDpia.isPending} onClick={() => createDpia.mutate()}>
            Start DPIA
          </Button>
        </CardContent>
        <CardContent className="pt-0 pb-4">
          <p className="text-xs text-[var(--fg-subtle)]">
            A high-risk DPIA automatically requires an Approval before it can be marked approved
            (GDPR Article 35).
          </p>
        </CardContent>
      </Card>
      {dpias?.length === 0 && <p className="text-sm text-[var(--fg-muted)]">No DPIAs recorded yet.</p>}
      <div className="flex flex-col gap-2">
        {dpias?.map((dpia) => (
          <Link key={dpia.id} href={`/compliance/dpias/${dpia.id}`}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{dpia.title}</div>
                  {dpia.ai_system_id && (
                    <div className="text-xs text-[var(--fg-subtle)]">Linked to an AI system</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={dpia.risk_level} />
                  <StatusBadge status={dpia.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function DSARSection() {
  const queryClient = useQueryClient();
  const [requesterName, setRequesterName] = useState("");
  const [requesterEmail, setRequesterEmail] = useState("");
  const [requestType, setRequestType] = useState<DSARRequestType>("access");

  const { data: dsars } = useQuery<DSAR[]>({
    queryKey: ["compliance", "dsars"],
    queryFn: () => apiFetch<DSAR[]>("/api/v1/compliance/dsars"),
  });

  const createDsar = useMutation({
    mutationFn: () =>
      apiFetch<DSAR>("/api/v1/compliance/dsars", {
        method: "POST",
        body: {
          requester_name: requesterName,
          requester_email: requesterEmail,
          request_type: requestType,
        },
      }),
    onSuccess: () => {
      setRequesterName("");
      setRequesterEmail("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "dsars"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Data Subject Access Requests (DSAR)
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <Input
            placeholder="Requester name"
            value={requesterName}
            onChange={(e) => setRequesterName(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <Input
            placeholder="Requester email"
            value={requesterEmail}
            onChange={(e) => setRequesterEmail(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <select
            className={selectClassName}
            value={requestType}
            onChange={(e) => setRequestType(e.target.value as DSARRequestType)}
          >
            <option value="access">Access</option>
            <option value="deletion">Deletion</option>
            <option value="rectification">Rectification</option>
            <option value="portability">Portability</option>
          </select>
          <Button
            disabled={!requesterName.trim() || !requesterEmail.trim() || createDsar.isPending}
            onClick={() => createDsar.mutate()}
          >
            Log DSAR
          </Button>
        </CardContent>
        <CardContent className="pt-0 pb-4">
          <p className="text-xs text-[var(--fg-subtle)]">
            Due 30 days from receipt (GDPR Article 12(3)).
          </p>
        </CardContent>
      </Card>
      {dsars?.length === 0 && <p className="text-sm text-[var(--fg-muted)]">No DSARs logged yet.</p>}
      <div className="flex flex-col gap-2">
        {dsars?.map((dsar) => (
          <Link key={dsar.id} href={`/compliance/dsars/${dsar.id}`}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{dsar.requester_name}</div>
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {dsar.request_type} · due {new Date(dsar.due_at).toLocaleDateString()}
                  </div>
                </div>
                <StatusBadge status={dsar.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function DataTransfersSection() {
  const queryClient = useQueryClient();
  const [recipientName, setRecipientName] = useState("");
  const [destinationCountry, setDestinationCountry] = useState("");
  const [transferMechanism, setTransferMechanism] = useState<TransferMechanism>("sccs");

  const { data: transfers } = useQuery<DataTransfer[]>({
    queryKey: ["compliance", "data-transfers"],
    queryFn: () => apiFetch<DataTransfer[]>("/api/v1/compliance/data-transfers"),
  });

  const createTransfer = useMutation({
    mutationFn: () =>
      apiFetch<DataTransfer>("/api/v1/compliance/data-transfers", {
        method: "POST",
        body: {
          recipient_name: recipientName,
          destination_country: destinationCountry.toUpperCase(),
          transfer_mechanism: transferMechanism,
        },
      }),
    onSuccess: () => {
      setRecipientName("");
      setDestinationCountry("");
      setTransferMechanism("sccs");
      queryClient.invalidateQueries({ queryKey: ["compliance", "data-transfers"] });
      queryClient.invalidateQueries({ queryKey: ["compliance", "risks"] });
    },
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status: newStatus }: { id: string; status: DataTransferStatus }) =>
      apiFetch(`/api/v1/compliance/data-transfers/${id}/status`, {
        method: "PATCH",
        body: { status: newStatus },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "data-transfers"] }),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Data Transfers
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-2 pt-6">
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="Recipient name"
              value={recipientName}
              onChange={(e) => setRecipientName(e.target.value)}
              className="min-w-[200px] flex-1"
            />
            <Input
              placeholder="Destination country (e.g. US)"
              value={destinationCountry}
              onChange={(e) => setDestinationCountry(e.target.value)}
              maxLength={2}
              className="w-40"
            />
            <select
              className={selectClassName}
              value={transferMechanism}
              onChange={(e) => setTransferMechanism(e.target.value as TransferMechanism)}
            >
              <option value="adequacy_decision">Adequacy decision</option>
              <option value="sccs">Standard Contractual Clauses</option>
              <option value="bcrs">Binding Corporate Rules</option>
              <option value="derogation">Article 49 derogation</option>
            </select>
            <Button
              disabled={
                !recipientName.trim() ||
                destinationCountry.trim().length !== 2 ||
                createTransfer.isPending
              }
              onClick={() => createTransfer.mutate()}
            >
              Log transfer
            </Button>
          </div>
          <p className="text-xs text-[var(--fg-subtle)]">
            A transfer relying on an Article 49 derogation automatically creates a linked Risk
            in the Risk Register.
          </p>
        </CardContent>
      </Card>
      {transfers?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No data transfers recorded yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {transfers?.map((transfer) => (
          <Card key={transfer.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">{transfer.recipient_name}</div>
                <div className="text-xs text-[var(--fg-subtle)]">
                  {transfer.destination_country} · {transfer.transfer_mechanism.replace(/_/g, " ")}
                </div>
                {transfer.related_risk_id && (
                  <div className="text-xs text-[var(--critical-600)]">Linked risk created</div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <select
                  className={selectClassName}
                  value={transfer.status}
                  onChange={(e) =>
                    updateStatus.mutate({
                      id: transfer.id,
                      status: e.target.value as DataTransferStatus,
                    })
                  }
                >
                  <option value="active">Active</option>
                  <option value="under_review">Under review</option>
                  <option value="terminated">Terminated</option>
                </select>
                <StatusBadge status={transfer.status} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function PoliciesSection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");

  const { data: policies, isLoading, error } = useQuery<Policy[]>({
    queryKey: ["compliance", "policies"],
    queryFn: () => apiFetch<Policy[]>("/api/v1/compliance/policies"),
  });

  const createPolicy = useMutation({
    mutationFn: () =>
      apiFetch<Policy>("/api/v1/compliance/policies", { method: "POST", body: { title } }),
    onSuccess: () => {
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "policies"] });
    },
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiFetch<Policy>(`/api/v1/compliance/policies/${id}/status`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance", "policies"] }),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Policies
      </h2>
      <Card className="mb-4">
        <CardContent className="flex gap-2 pt-6">
          <Input
            placeholder="Policy title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Button disabled={!title.trim() || createPolicy.isPending} onClick={() => createPolicy.mutate()}>
            Add policy
          </Button>
        </CardContent>
      </Card>
      {isLoading && <p className="text-sm text-[var(--fg-muted)]">Loading…</p>}
      {error && <p className="text-sm text-[var(--critical-600)]">Could not load policies.</p>}
      {policies?.length === 0 && <p className="text-sm text-[var(--fg-muted)]">No policies yet.</p>}
      <div className="flex flex-col gap-2">
        {policies?.map((policy) => (
          <Card key={policy.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div className="font-medium text-[var(--fg-default)]">{policy.title}</div>
              <div className="flex items-center gap-2">
                <select
                  className={selectClassName}
                  value={policy.status}
                  onChange={(e) => updateStatus.mutate({ id: policy.id, status: e.target.value })}
                >
                  <option value="draft">Draft</option>
                  <option value="published">Published</option>
                </select>
                <StatusBadge status={policy.status} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

async function uploadEvidenceFile(file: File, title: string): Promise<void> {
  const { file_id, upload_url } = await apiFetch<{ file_id: string; upload_url: string }>(
    "/api/v1/files/upload-url",
    {
      method: "POST",
      body: {
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
        classification: "internal",
      },
    },
  );

  const putResponse = await fetch(upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  if (!putResponse.ok) {
    throw new Error(`Upload to storage failed with status ${putResponse.status}`);
  }

  await apiFetch("/api/v1/compliance/evidence", {
    method: "POST",
    body: { file_id, title: title || file.name },
  });
}

function EvidenceLibrarySection() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data: evidence, isLoading, error } = useQuery<Evidence[]>({
    queryKey: ["compliance", "evidence"],
    queryFn: () => apiFetch<Evidence[]>("/api/v1/compliance/evidence"),
  });

  const upload = useMutation({
    mutationFn: (file: File) => uploadEvidenceFile(file, title),
    onSuccess: () => {
      setTitle("");
      setUploadError(null);
      queryClient.invalidateQueries({ queryKey: ["compliance", "evidence"] });
    },
    onError: (err) => setUploadError(err instanceof ApiError ? err.message : "Upload failed"),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Evidence Library
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-center gap-2 pt-6">
          <Input
            placeholder="Evidence title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="max-w-xs"
          />
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
              e.target.value = "";
            }}
          />
          <Button
            variant="outline"
            disabled={upload.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            {upload.isPending ? "Uploading…" : "Upload evidence"}
          </Button>
          {uploadError && <p className="text-sm text-[var(--critical-600)]">{uploadError}</p>}
        </CardContent>
      </Card>
      {isLoading && <p className="text-sm text-[var(--fg-muted)]">Loading…</p>}
      {error && <p className="text-sm text-[var(--critical-600)]">Could not load evidence.</p>}
      {evidence?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No evidence uploaded yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {evidence?.map((item) => (
          <Card key={item.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div className="font-medium text-[var(--fg-default)]">{item.title}</div>
              <div className="flex gap-2">
                {item.control_id && <Badge variant="secondary">linked to control</Badge>}
                {item.vendor_id && <Badge variant="secondary">linked to vendor</Badge>}
                {item.valid_until && (
                  <Badge variant="outline">
                    valid until {new Date(item.valid_until).toLocaleDateString()}
                  </Badge>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function FrameworksSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const { data: frameworks } = useQuery<Framework[]>({
    queryKey: ["compliance", "frameworks"],
    queryFn: () => apiFetch<Framework[]>("/api/v1/compliance/frameworks"),
  });

  const createFramework = useMutation({
    mutationFn: () =>
      apiFetch<Framework>("/api/v1/compliance/frameworks", {
        method: "POST",
        body: { name, requirements: [] },
      }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "frameworks"] });
    },
  });

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Frameworks
      </h2>
      <div className="mb-3 flex flex-wrap gap-2">
        {frameworks?.map((framework) => (
          <Link key={framework.id} href={`/compliance/frameworks/${framework.id}`}>
            <Badge variant="secondary" className="cursor-pointer hover:bg-[var(--gray-200)]">
              {framework.name}
              {framework.is_custom && " (custom)"}
            </Badge>
          </Link>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="Custom framework name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="min-w-[200px] flex-1"
        />
        <Button
          size="sm"
          disabled={!name.trim() || createFramework.isPending}
          onClick={() => createFramework.mutate()}
        >
          Add custom framework
        </Button>
      </div>
    </div>
  );
}

const COMPLIANCE_GROUPS: { label: string; render: () => React.ReactNode }[] = [
  {
    label: "Controls & Risk",
    render: () => (
      <>
        <ControlsSection />
        <RisksSection />
        <EvidenceLibrarySection />
        <PoliciesSection />
      </>
    ),
  },
  {
    label: "Assessments",
    render: () => (
      <>
        <QuestionnairesSection />
        <AuditsSection />
        <SecurityReviewsSection />
      </>
    ),
  },
  {
    label: "AI Governance",
    render: () => (
      <>
        <AISystemsSection />
        <AIIncidentsSection />
      </>
    ),
  },
  {
    label: "Privacy",
    render: () => (
      <>
        <ProcessingActivitiesSection />
        <DPIASection />
        <DSARSection />
        <DataTransfersSection />
      </>
    ),
  },
  {
    label: "Vendors & Trust",
    render: () => (
      <>
        <VendorsSection />
        <TrustCenterSection />
      </>
    ),
  },
  { label: "Frameworks", render: () => <FrameworksSection /> },
];

export default function CompliancePage() {
  return (
    <div>
      <PageHeader
        title="Compliance"
        description="Frameworks, controls, evidence, and risk. A Framework's Requirements are met by Controls, which are proven by Evidence and Assessments — gaps become Risks and Tasks."
      />
      <div className="flex flex-col gap-10">
        {COMPLIANCE_GROUPS.map((group) => (
          <section key={group.label}>
            <h2 className="mb-4 border-b border-[var(--border-default)] pb-2 text-sm font-semibold text-[var(--fg-default)]">
              {group.label}
            </h2>
            {group.render()}
          </section>
        ))}
      </div>
    </div>
  );
}
