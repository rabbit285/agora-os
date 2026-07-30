"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type {
  AIIncident,
  AIRiskClassification,
  AISystem,
  Control,
  DPIA,
  DPIARiskLevel,
  DSAR,
  DSARRequestType,
  Framework,
  LegalBasis,
  ProcessingActivity,
  Questionnaire,
  QuestionnaireSource,
  Risk,
  Severity,
  Vendor,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
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
      {controls?.length === 0 && <p className="text-sm text-neutral-500">No controls yet.</p>}
      <div className="flex flex-col gap-2">
        {controls?.map((control) => (
          <Link key={control.id} href={`/compliance/controls/${control.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div className="font-medium text-neutral-900">{control.title}</div>
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Risk Register
      </h2>
      {risks?.length === 0 && <p className="text-sm text-neutral-500">No risks recorded.</p>}
      <div className="flex flex-col gap-2">
        {risks?.map((risk) => (
          <Card key={risk.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">{risk.title}</div>
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
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
      {vendors?.length === 0 && <p className="text-sm text-neutral-500">No vendors recorded yet.</p>}
      <div className="flex flex-col gap-2">
        {vendors?.map((vendor) => (
          <Link key={vendor.id} href={`/compliance/vendors/${vendor.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{vendor.name}</div>
                  <div className="text-xs text-neutral-400">{vendor.category}</div>
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
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
        <p className="text-sm text-neutral-500">No questionnaires yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {questionnaires?.map((questionnaire) => (
          <Link
            key={questionnaire.id}
            href={`/compliance/questionnaires/${questionnaire.id}`}
          >
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{questionnaire.title}</div>
                  <div className="text-xs text-neutral-400">
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
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
          <p className="text-xs text-neutral-400">
            High or unacceptable-risk systems automatically require an Approval before they can be
            marked approved (spec section 69 — New AI Tool Adoption).
          </p>
        </CardContent>
      </Card>
      {aiSystems?.length === 0 && (
        <p className="text-sm text-neutral-500">No AI systems registered yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {aiSystems?.map((system) => (
          <Link key={system.id} href={`/compliance/ai-systems/${system.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{system.name}</div>
                  {system.vendor && (
                    <div className="text-xs text-neutral-400">{system.vendor}</div>
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
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
          <p className="text-xs text-neutral-400">
            A critical incident automatically creates a linked Risk and response Task, and
            notifies the incident owner (EU AI Act Article 73 serious-incident obligations).
          </p>
        </CardContent>
      </Card>
      {incidents?.length === 0 && (
        <p className="text-sm text-neutral-500">No AI incidents logged yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {incidents?.map((incident) => (
          <Link key={incident.id} href={`/compliance/ai-incidents/${incident.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{incident.title}</div>
                  <div className="text-xs text-neutral-400">
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
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
        <p className="text-sm text-neutral-500">No processing activities recorded yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {activities?.map((activity) => (
          <Card key={activity.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">{activity.name}</div>
                <div className="text-xs text-neutral-400">
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
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
          <p className="text-xs text-neutral-400">
            A high-risk DPIA automatically requires an Approval before it can be marked approved
            (GDPR Article 35).
          </p>
        </CardContent>
      </Card>
      {dpias?.length === 0 && <p className="text-sm text-neutral-500">No DPIAs recorded yet.</p>}
      <div className="flex flex-col gap-2">
        {dpias?.map((dpia) => (
          <Link key={dpia.id} href={`/compliance/dpias/${dpia.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{dpia.title}</div>
                  {dpia.ai_system_id && (
                    <div className="text-xs text-neutral-400">Linked to an AI system</div>
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
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
          <p className="text-xs text-neutral-400">
            Due 30 days from receipt (GDPR Article 12(3)).
          </p>
        </CardContent>
      </Card>
      {dsars?.length === 0 && <p className="text-sm text-neutral-500">No DSARs logged yet.</p>}
      <div className="flex flex-col gap-2">
        {dsars?.map((dsar) => (
          <Link key={dsar.id} href={`/compliance/dsars/${dsar.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{dsar.requester_name}</div>
                  <div className="text-xs text-neutral-400">
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

function FrameworksSection() {
  const { data: frameworks } = useQuery<Framework[]>({
    queryKey: ["compliance", "frameworks"],
    queryFn: () => apiFetch<Framework[]>("/api/v1/compliance/frameworks"),
  });

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Frameworks
      </h2>
      <div className="flex flex-wrap gap-2">
        {frameworks?.map((framework) => (
          <Badge key={framework.id} variant="secondary">
            {framework.name}
          </Badge>
        ))}
      </div>
    </div>
  );
}

export default function CompliancePage() {
  return (
    <div>
      <PageHeader
        title="Compliance"
        description="Frameworks, controls, evidence, and risk — spec section 12."
      />
      <ControlsSection />
      <RisksSection />
      <VendorsSection />
      <QuestionnairesSection />
      <AISystemsSection />
      <AIIncidentsSection />
      <ProcessingActivitiesSection />
      <DPIASection />
      <DSARSection />
      <FrameworksSection />
    </div>
  );
}
