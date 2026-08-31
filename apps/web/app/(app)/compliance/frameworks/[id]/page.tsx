"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  FileWarning,
  Info,
  MoreHorizontal,
} from "lucide-react";

import { AttachEvidence } from "@/components/compliance/attach-evidence";
import { MapControl } from "@/components/compliance/map-control";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  ComplianceGap,
  FrameworkActivation,
  FrameworkAssessmentResult,
  FrameworkDashboard,
  FrameworkDashboardRequirement,
  RequirementStatus,
} from "@/lib/types";

/** How each assessed position is presented. The labels avoid asserting a
 * legal conclusion: "Evidence missing" describes the state of our record,
 * where "Non-compliant" would be a verdict this system is not entitled to
 * reach. See app/compliance/assessment.py for the same reasoning. */
/** One label per state, and the labels say what the state means.
 *
 * The previous map had `partial` reading "Needs review" and
 * `needs_review` reading "Assessment failed" — two states crossed over
 * each other, which is why one requirement could show "Needs review"
 * beside a confirmed gap and a Remediating badge. */
const STATUS_PRESENTATION: Record<
  RequirementStatus,
  { label: string; variant: "success" | "destructive" | "secondary" | "outline"; icon: typeof Info }
> = {
  satisfied: { label: "Satisfied", variant: "success", icon: CheckCircle2 },
  needs_review: { label: "Awaiting review", variant: "secondary", icon: Info },
  deficient: { label: "Gap identified", variant: "destructive", icon: AlertTriangle },
  assessment_failed: { label: "Assessment failed", variant: "destructive", icon: AlertTriangle },
  evidence_missing: { label: "Evidence missing", variant: "destructive", icon: FileWarning },
  not_assessed: { label: "No control mapped", variant: "outline", icon: CircleDashed },
  not_applicable: { label: "Does not apply", variant: "outline", icon: CircleDashed },
};

/** The last recorded human verdict, in words.
 *
 * Null means nobody has recorded one — which is "Assessment pending",
 * not "none" and certainly not the internal `nothing yet` this used to
 * surface. A missing assessment is a step not yet taken, and saying so
 * tells the reader what happens next. */
const ASSESSMENT_LABEL: Record<string, string> = {
  pass: "Assessed as passing",
  fail: "Assessed as failing",
  partial: "Partially assessed",
  not_assessed: "Assessment pending",
};

/** Manual mapping and attachment, demoted.
 *
 * These are the escape hatch for when document intelligence did not
 * find something — real, but not the path the product wants anyone on.
 * Keeping them as primary buttons beside every requirement taught the
 * customer to do by hand the work they bought this to avoid. */
function RequirementActions({
  requirement,
  frameworkId,
  onChanged,
}: {
  requirement: FrameworkDashboardRequirement;
  frameworkId: string;
  onChanged: () => void;
}) {
  const [mapping, setMapping] = useState(false);
  const [attachingTo, setAttachingTo] = useState<string | null>(null);

  return (
    <div className="w-full">
      {!mapping && attachingTo === null && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="ghost">
              <MoreHorizontal className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
              More
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Do this by hand</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setMapping(true)}>
              Map another control
            </DropdownMenuItem>
            {/* Offered per mapped control rather than once per
                requirement: evidence attaches to a control, and a
                requirement answered by two controls needs to say which
                one a document supports. */}
            {requirement.controls.map((control) => (
              <DropdownMenuItem
                key={control.id}
                onSelect={() => setAttachingTo(control.id)}
              >
                {requirement.controls.length > 1
                  ? `Attach evidence to ${control.title}`
                  : "Attach evidence"}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      <MapControl
        requirementId={requirement.id}
        requirementCode={requirement.reference_code}
        frameworkId={frameworkId}
        mappedControlIds={requirement.controls.map((c) => c.id)}
        open={mapping}
        onOpenChange={setMapping}
      />

      {requirement.controls.map((control) => (
        <AttachEvidence
          key={control.id}
          controlId={control.id}
          compact
          open={attachingTo === control.id}
          onOpenChange={(next) => setAttachingTo(next ? control.id : null)}
          onAttached={onChanged}
        />
      ))}
    </div>
  );
}

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
              <Stat label="Readiness" value={`${result.readiness.percent}%`} />
              <Stat label="Satisfied" value={`${result.satisfied_count}/${result.requirements.length}`} />
              <Stat label="Evidence coverage" value={`${result.evidence_coverage_percent}%`} />
              <Stat label="Open gaps" value={String(result.gap_count)} />
              <p className="ml-auto text-xs text-[var(--fg-subtle)]">
                Assessed {new Date(result.assessed_at).toLocaleString()}
              </p>
            </div>

            {/* The score never appears without its arithmetic. A bare
                percentage is not something the person accountable for it
                can act on — their next question is always "which ones". */}
            <p className="mt-4 rounded-[var(--radius-md)] bg-[var(--bg-app)] p-3 text-sm leading-relaxed text-[var(--fg-default)]">
              {result.readiness.explanation}
            </p>

            <p className="mt-3 text-xs leading-relaxed text-[var(--fg-subtle)]">
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

                {evaluation && evaluation.missing_conditions.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
                      Not covered by the evidence on file
                    </p>
                    <ul className="mt-1 flex flex-col gap-1">
                      {evaluation.missing_conditions.map((condition) => (
                        <li
                          key={condition}
                          className="flex items-start gap-2 text-sm text-[var(--fg-muted)]"
                        >
                          <FileWarning className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                          <span>{condition}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {evaluation && evaluation.status !== "not_applicable" && (
                  <p className="mt-2 text-xs text-[var(--fg-subtle)]">
                    {evaluation.evidence_count} evidence item
                    {evaluation.evidence_count === 1 ? "" : "s"} ·{" "}
                    {evaluation.control_ids.length} control
                    {evaluation.control_ids.length === 1 ? "" : "s"} ·{" "}
                    {ASSESSMENT_LABEL[evaluation.latest_assessment_status ?? ""] ??
                      "Assessment pending"}
                  </p>
                )}

                {/* Mapping and attaching by hand are the fallback, not the
                    workflow. Once a control is mapped they are demoted to a
                    More menu: the product's own answer to "what do I do
                    next" is to upload a document and let it be read, and a
                    row of manual buttons beside every requirement argues
                    the opposite. They stay primary while nothing is mapped,
                    because then there genuinely is nothing else to do. */}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {requirement.controls.length === 0 ? (
                    <MapControl
                      requirementId={requirement.id}
                      requirementCode={requirement.reference_code}
                      frameworkId={id}
                      mappedControlIds={[]}
                    />
                  ) : (
                    <RequirementActions
                      requirement={requirement}
                      frameworkId={id}
                      onChanged={() => {
                        void queryClient.invalidateQueries({
                          queryKey: ["compliance", "frameworks", id, "dashboard"],
                        });
                      }}
                    />
                  )}
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

const SEVERITY_LABEL: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

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

  // Empty body on purpose. The remediation plan already carries a
  // priority derived from severity and a due date derived from how long
  // the work actually takes; sending "high / 7 days" from here gave a
  // training programme the same deadline as a one-line policy edit.
  const createTask = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/gaps/${gap.id}/task`, {
        method: "POST",
        body: {},
      }),
    onSuccess: invalidate,
  });

  const error = remediation.error ?? createTask.error;

  return (
    <div className="mt-4 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-[var(--warning-700)]">
        <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
        Gap · {SEVERITY_LABEL[gap.severity] ?? "Medium"} severity
        {gap.status === "remediating" && (
          <Badge variant="secondary" className="ml-1">
            Remediating
          </Badge>
        )}
      </p>

      {gap.remediation_plan ? (
        <div className="mt-2 text-sm leading-relaxed text-[var(--warning-700)]">
          <p>{gap.remediation_plan.problem}</p>
          <p className="mt-2 font-medium">{gap.remediation_plan.action}</p>
          <p className="mt-2 text-[var(--warning-700)]/80">
            {gap.remediation_plan.checklist.length} steps · suggested owner{" "}
            {gap.remediation_plan.owner}
          </p>
        </div>
      ) : gap.recommendation ? (
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
        {!gap.remediation_plan && (
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
