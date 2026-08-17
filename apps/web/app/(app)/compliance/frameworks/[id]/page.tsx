"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleDashed, FileWarning, Info } from "lucide-react";

import { AttachEvidence } from "@/components/compliance/attach-evidence";
import { MapControl } from "@/components/compliance/map-control";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  ComplianceGap,
  FrameworkActivation,
  FrameworkAssessmentResult,
  FrameworkDashboard,
  RequirementEvaluation,
} from "@/lib/types";

/** How each assessed position is presented. The labels avoid asserting a
 * legal conclusion: "Evidence missing" describes the state of our record,
 * where "Non-compliant" would be a verdict this system is not entitled to
 * reach. See app/compliance/assessment.py for the same reasoning. */
const STATUS_PRESENTATION: Record<
  RequirementEvaluation["status"],
  { label: string; variant: "success" | "destructive" | "secondary" | "outline"; icon: typeof Info }
> = {
  satisfied: { label: "Satisfied", variant: "success", icon: CheckCircle2 },
  partial: { label: "Needs review", variant: "secondary", icon: Info },
  needs_review: { label: "Assessment failed", variant: "destructive", icon: AlertTriangle },
  evidence_missing: { label: "Evidence missing", variant: "destructive", icon: FileWarning },
  not_assessed: { label: "No control mapped", variant: "outline", icon: CircleDashed },
};

export default function FrameworkDashboardPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [result, setResult] = useState<FrameworkAssessmentResult | null>(null);

  const { data, isLoading, error } = useQuery<FrameworkDashboard>({
    queryKey: ["compliance", "frameworks", id, "dashboard"],
    queryFn: () => apiFetch<FrameworkDashboard>(`/api/v1/compliance/frameworks/${id}/dashboard`),
  });

  const { data: activations } = useQuery<FrameworkActivation[]>({
    queryKey: ["compliance", "frameworks", "activations"],
    queryFn: () => apiFetch<FrameworkActivation[]>("/api/v1/compliance/frameworks/activations"),
  });

  const { data: gaps } = useQuery<ComplianceGap[]>({
    queryKey: ["compliance", "gaps", id],
    queryFn: () => apiFetch<ComplianceGap[]>(`/api/v1/compliance/gaps?framework_id=${id}`),
  });

  const isActive =
    activations?.find((a) => a.framework_id === id)?.status === "active";

  const setActivation = useMutation({
    mutationFn: (active: boolean) =>
      apiFetch<FrameworkActivation>(`/api/v1/compliance/frameworks/${id}/activation`, {
        method: "PUT",
        body: { active },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "frameworks", "activations"] }),
  });

  const assess = useMutation({
    mutationFn: () =>
      apiFetch<FrameworkAssessmentResult>(`/api/v1/compliance/frameworks/${id}/assess`, {
        method: "POST",
      }),
    onSuccess: (data) => {
      setResult(data);
      void queryClient.invalidateQueries({ queryKey: ["compliance", "gaps", id] });
      void queryClient.invalidateQueries({
        queryKey: ["compliance", "frameworks", id, "dashboard"],
      });
    },
  });

  if (isLoading) return <p className="text-sm text-[var(--fg-muted)]">Loading…</p>;
  if (error) {
    return (
      <p className="text-sm text-[var(--critical-600)]">
        {error instanceof ApiError ? error.message : "Could not load this framework."}
      </p>
    );
  }
  if (!data) return null;

  const gapByRequirement = new Map((gaps ?? []).map((g) => [g.requirement_id, g]));
  const evaluationByRequirement = new Map(
    (result?.requirements ?? []).map((r) => [r.requirement_id, r]),
  );

  return (
    <div>
      <PageHeader
        title={data.framework.name}
        description={data.framework.description ?? undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={isActive ? "success" : "outline"}>
              {isActive ? "Active" : "Not active"}
            </Badge>
            <Button
              size="sm"
              variant="outline"
              disabled={setActivation.isPending}
              onClick={() => setActivation.mutate(!isActive)}
            >
              {isActive ? "Deactivate" : "Activate"}
            </Button>
            <Button size="sm" disabled={assess.isPending} onClick={() => assess.mutate()}>
              {assess.isPending ? "Assessing…" : result ? "Reassess" : "Run assessment"}
            </Button>
          </div>
        }
      />

      {(setActivation.error || assess.error) && (
        <p className="mb-4 text-sm text-[var(--critical-600)]">
          {(setActivation.error ?? assess.error) instanceof ApiError
            ? (setActivation.error ?? assess.error)!.message
            : "Something went wrong."}
        </p>
      )}

      {result && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <div className="flex flex-wrap items-center gap-6">
              <Stat label="Satisfied" value={`${result.satisfied_count}/${result.requirements.length}`} />
              <Stat label="Evidence coverage" value={`${result.evidence_coverage_percent}%`} />
              <Stat label="Open gaps" value={String(result.gap_count)} />
              <p className="ml-auto text-xs text-[var(--fg-subtle)]">
                Assessed {new Date(result.assessed_at).toLocaleString()}
              </p>
            </div>
            <p className="mt-4 text-xs leading-relaxed text-[var(--fg-subtle)]">
              Statuses are computed from mapped controls, attached evidence, and recorded
              assessments — not inferred. A requirement with no evidence means nothing
              demonstrating it has been found in Veyntra, which is not a finding that the
              requirement is unmet.
            </p>
          </CardContent>
        </Card>
      )}

      {data.requirements.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">This framework has no requirements yet.</p>
      )}

      <div className="flex flex-col gap-3">
        {data.requirements.map((requirement) => {
          const evaluation = evaluationByRequirement.get(requirement.id);
          const gap = gapByRequirement.get(requirement.id);
          const presentation = evaluation ? STATUS_PRESENTATION[evaluation.status] : null;

          return (
            <Card key={requirement.id}>
              <CardContent className="pt-6">
                <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <span className="font-mono text-xs text-[var(--fg-subtle)]">
                      {requirement.reference_code}
                    </span>
                    <div className="font-medium text-[var(--fg-default)]">{requirement.title}</div>
                  </div>
                  {presentation ? (
                    <Badge variant={presentation.variant} className="gap-1">
                      <presentation.icon className="h-3 w-3" aria-hidden="true" />
                      {presentation.label}
                    </Badge>
                  ) : (
                    requirement.controls.length === 0 && (
                      <Badge variant="outline">No control mapped</Badge>
                    )
                  )}
                </div>

                {requirement.controls.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {requirement.controls.map((control) => (
                      <Link key={control.id} href={`/compliance/controls/${control.id}`}>
                        <Badge
                          variant="secondary"
                          className="cursor-pointer hover:bg-[var(--gray-200)]"
                        >
                          {control.title}
                        </Badge>
                      </Link>
                    ))}
                  </div>
                )}

                {evaluation && (
                  <p className="mt-3 text-sm leading-relaxed text-[var(--fg-muted)]">
                    {evaluation.summary}
                  </p>
                )}

                {evaluation && (
                  <p className="mt-2 text-xs text-[var(--fg-subtle)]">
                    {evaluation.evidence_count} evidence item
                    {evaluation.evidence_count === 1 ? "" : "s"} ·{" "}
                    {evaluation.control_ids.length} control
                    {evaluation.control_ids.length === 1 ? "" : "s"} · last assessment:{" "}
                    {evaluation.latest_assessment_status ?? "none"}
                  </p>
                )}

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <MapControl
                    requirementId={requirement.id}
                    requirementCode={requirement.reference_code}
                    frameworkId={id}
                    mappedControlIds={requirement.controls.map((c) => c.id)}
                  />
                  {/* Offered per mapped control rather than once per
                      requirement: evidence attaches to a control, and a
                      requirement answered by two controls needs to say
                      which one a document supports. */}
                  {requirement.controls.map((control) => (
                    <AttachEvidence
                      key={control.id}
                      controlId={control.id}
                      label={
                        requirement.controls.length > 1
                          ? `Attach evidence to ${control.title}`
                          : "Attach evidence"
                      }
                      compact
                      onAttached={() => {
                        void queryClient.invalidateQueries({
                          queryKey: ["compliance", "frameworks", id, "dashboard"],
                        });
                      }}
                    />
                  ))}
                </div>

                {gap && gap.status !== "resolved" && (
                  <GapPanel gap={gap} frameworkId={id} />
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">{label}</p>
      <p className="text-xl font-semibold text-[var(--fg-default)]">{value}</p>
    </div>
  );
}

/** The gap, its recommendation, and the two actions that move it forward.
 * Kept inline with the requirement rather than on a separate screen: the
 * reader is already looking at the thing that is deficient. */
function GapPanel({ gap, frameworkId }: { gap: ComplianceGap; frameworkId: string }) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["compliance", "gaps", frameworkId] });

  const remediation = useMutation({
    mutationFn: () =>
      apiFetch<ComplianceGap>(`/api/v1/compliance/gaps/${gap.id}/remediation`, {
        method: "POST",
      }),
    onSuccess: invalidate,
  });

  const createTask = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/gaps/${gap.id}/task`, {
        method: "POST",
        body: { due_in_days: 7, priority: "high" },
      }),
    onSuccess: invalidate,
  });

  const error = remediation.error ?? createTask.error;

  return (
    <div className="mt-4 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-[var(--warning-700)]">
        <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
        Gap · {gap.severity} severity
        {gap.status === "remediating" && (
          <Badge variant="secondary" className="ml-1">
            Remediating
          </Badge>
        )}
      </p>

      {gap.recommendation ? (
        <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-[var(--warning-700)]">
          {gap.recommendation}
        </p>
      ) : (
        <p className="mt-2 text-sm text-[var(--warning-700)]">
          No remediation has been generated for this gap yet.
        </p>
      )}

      {error && (
        <p className="mt-2 text-sm text-[var(--critical-600)]">
          {error instanceof ApiError ? error.message : "Something went wrong."}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {!gap.recommendation && (
          <Button
            size="sm"
            variant="outline"
            disabled={remediation.isPending}
            onClick={() => remediation.mutate()}
          >
            {remediation.isPending ? "Generating…" : "Generate remediation"}
          </Button>
        )}
        {gap.task_id ? (
          <Button size="sm" variant="outline" asChild>
            <Link href={`/tasks/${gap.task_id}`}>View remediation task</Link>
          </Button>
        ) : (
          <Button size="sm" disabled={createTask.isPending} onClick={() => createTask.mutate()}>
            {createTask.isPending ? "Creating…" : "Create task"}
          </Button>
        )}
      </div>
    </div>
  );
}
