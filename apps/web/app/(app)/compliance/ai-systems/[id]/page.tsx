"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { AiPrivacyAssessment } from "@/components/compliance/ai-privacy-assessment";
import { EuAiActScreening } from "@/components/compliance/eu-ai-act-screening";
import type {
  AIAssessmentDetail,
  Approval,
  AISystemDetail,
  AISystemStatus,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

export default function AISystemDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [assessmentStatus, setAssessmentStatus] = useState<
    "pass" | "fail" | "partial" | "not_assessed"
  >("pass");
  const [assessmentNotes, setAssessmentNotes] = useState("");

  const { data: system } = useQuery<AISystemDetail>({
    queryKey: ["compliance", "ai-systems", id],
    queryFn: () => apiFetch<AISystemDetail>(`/api/v1/compliance/ai-systems/${id}`),
  });

  const { data: approvals } = useQuery<Approval[]>({
    queryKey: ["approvals"],
    queryFn: () => apiFetch<Approval[]>("/api/v1/approvals"),
    enabled: !!system?.approval_id,
  });

  const updateStatus = useMutation({
    mutationFn: (status: AISystemStatus) =>
      apiFetch(`/api/v1/compliance/ai-systems/${id}/status`, { method: "PATCH", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance", "ai-systems", id] }),
  });

  const addAssessment = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/ai-systems/${id}/assessments`, {
        method: "POST",
        body: { status: assessmentStatus, notes: assessmentNotes || null },
      }),
    onSuccess: () => {
      setAssessmentNotes("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "ai-systems", id] });
    },
  });

  if (!system) return null;

  const linkedApproval = approvals?.find((a) => a.id === system.approval_id);

  // Typed assessments are picked out by kind rather than by position:
  // the EU AI Act screening and the privacy review are different records
  // answering to different regulators, and each panel shows its own
  // latest. `assessments` arrives newest-first from the API.
  const typed = system.assessments as unknown as AIAssessmentDetail[];
  const latestScreening = typed.find((a) => a.assessment_type === "eu_ai_act");
  const latestPrivacy = typed.find((a) => a.assessment_type === "privacy");

  return (
    <div>
      <PageHeader
        title={system.name}
        description={system.purpose}
        actions={<StatusBadge status={system.risk_classification} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {system.vendor && (
          <span className="text-sm text-[var(--fg-muted)]">Vendor: {system.vendor}</span>
        )}
        <span className="text-sm text-[var(--fg-muted)]">Status:</span>
        <StatusBadge status={system.status} />
        <select
          className={selectClassName}
          value={system.status}
          onChange={(e) => updateStatus.mutate(e.target.value as AISystemStatus)}
        >
          <option value="in_review">In review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="retired">Retired</option>
        </select>
        {updateStatus.isError && (
          <span className="text-xs text-[var(--critical-600)]">
            {(updateStatus.error as Error).message}
          </span>
        )}
      </div>

      <AiSystemProfile system={system} />

      <EuAiActScreening aiSystemId={id} latest={latestScreening} />

      <AiPrivacyAssessment aiSystemId={id} latest={latestPrivacy} />

      {system.approval_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
              Required Approval
            </h2>
            <p className="mb-2 text-xs text-[var(--fg-subtle)]">
              This system&apos;s risk classification automatically required sign-off before it can
              be marked approved (spec section 69 — New AI Tool Adoption).
            </p>
            {linkedApproval ? (
              <div className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
                <Link href="/approvals" className="hover:underline">
                  {linkedApproval.action_type}
                </Link>
                <StatusBadge status={linkedApproval.status} />
              </div>
            ) : (
              <span className="text-sm text-[var(--fg-subtle)]">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Assessments
        </h2>
        <div className="mb-4 flex flex-col gap-2">
          {system.assessments.length === 0 && (
            <p className="text-sm text-[var(--fg-muted)]">No assessments yet.</p>
          )}
          {system.assessments.map((assessment) => (
            <Card key={assessment.id}>
              <CardContent className="flex items-center justify-between pt-6">
                <div className="text-sm text-[var(--fg-muted)]">{assessment.notes ?? "—"}</div>
                <StatusBadge status={assessment.status} />
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardContent className="flex flex-wrap gap-2 pt-6">
            <select
              className={selectClassName}
              value={assessmentStatus}
              onChange={(e) =>
                setAssessmentStatus(
                  e.target.value as "pass" | "fail" | "partial" | "not_assessed",
                )
              }
            >
              <option value="pass">Pass</option>
              <option value="fail">Fail</option>
              <option value="partial">Partial</option>
              <option value="not_assessed">Not assessed</option>
            </select>
            <Input
              placeholder="Notes"
              value={assessmentNotes}
              onChange={(e) => setAssessmentNotes(e.target.value)}
              className="min-w-[200px] flex-1"
            />
            <Button disabled={addAssessment.isPending} onClick={() => addAssessment.mutate()}>
              Record assessment
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/** The inventory detail the EU AI Act expects: who operates the system,
 * who is affected by it without operating it, what data it touches, and
 * the specific model behind it.
 *
 * Editable inline rather than behind a separate screen, because these
 * fields are filled in over time by different people — the person who
 * registers a tool on Monday rarely knows the retention story yet. Empty
 * states say "not recorded" rather than rendering nothing, so a reader
 * can tell the difference between "none" and "nobody has said".
 */
function AiSystemProfile({ system }: { system: AISystemDetail }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [modelName, setModelName] = useState(system.model_name ?? "");
  const [internal, setInternal] = useState((system.internal_users ?? []).join(", "));
  const [affected, setAffected] = useState((system.affected_users ?? []).join(", "));

  const save = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/ai-systems/${system.id}/profile`, {
        method: "PATCH",
        body: {
          model_name: modelName || null,
          internal_users: internal
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          affected_users: affected
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        },
      }),
    onSuccess: () => {
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["compliance", "ai-systems", system.id] });
    },
  });

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-medium text-[var(--fg-default)]">System profile</h2>
          <Button size="sm" variant="outline" onClick={() => setEditing(!editing)}>
            {editing ? "Cancel" : "Edit"}
          </Button>
        </div>

        {editing ? (
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-[var(--fg-default)]">Model</span>
              <Input
                value={modelName}
                placeholder="e.g. claude-opus-4, or 'Demo model — no provider configured'"
                onChange={(e) => setModelName(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-[var(--fg-default)]">Internal users (comma separated)</span>
              <Input value={internal} onChange={(e) => setInternal(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-[var(--fg-default)]">
                Affected people who do not use it (comma separated)
              </span>
              <Input value={affected} onChange={(e) => setAffected(e.target.value)} />
            </label>
            <div>
              <Button disabled={save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? "Saving…" : "Save profile"}
              </Button>
            </div>
          </div>
        ) : (
          <dl className="grid gap-3 sm:grid-cols-2">
            <ProfileField label="Model" value={system.model_name} />
            <ProfileField
              label="Last reviewed"
              value={
                system.last_reviewed_at
                  ? new Date(system.last_reviewed_at).toLocaleDateString()
                  : null
              }
            />
            <ProfileField label="Internal users" value={(system.internal_users ?? []).join(", ")} />
            <ProfileField
              label="Affected people"
              value={(system.affected_users ?? []).join(", ")}
            />
            <div className="sm:col-span-2">
              <dt className="text-xs font-medium text-[var(--fg-subtle)]">Data processed</dt>
              <dd className="mt-1 flex flex-wrap gap-2">
                {(system.processed_data ?? []).length === 0 ? (
                  <span className="text-sm text-[var(--fg-subtle)]">Not recorded</span>
                ) : (
                  (system.processed_data ?? []).map((item) => (
                    <span
                      key={item.name}
                      className="rounded-full border border-[var(--border-default)] px-2.5 py-0.5 text-xs text-[var(--fg-muted)]"
                    >
                      {item.name}
                      <span className="ml-1 text-[var(--fg-subtle)]">· {item.classification}</span>
                    </span>
                  ))
                )}
              </dd>
            </div>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function ProfileField({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-xs font-medium text-[var(--fg-subtle)]">{label}</dt>
      <dd className="text-sm text-[var(--fg-muted)]">
        {value || <span className="text-[var(--fg-subtle)]">Not recorded</span>}
      </dd>
    </div>
  );
}
