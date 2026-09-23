"use client";

import Link from "next/link";
import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { DpiaCompletion } from "@/components/compliance/dpia-completion";
import { DpiaContextGaps } from "@/components/compliance/dpia-context-gaps";
import { DpiaRiskReview } from "@/components/compliance/dpia-risk-review";
import { DpiaScreeningPanel } from "@/components/compliance/dpia-screening-panel";
import { DpiaSections } from "@/components/compliance/dpia-sections";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { Approval, DPIAStatus, DpiaWorkflow } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

/** The lifecycle, in one control.
 *
 * The page used to show a status badge beside a dropdown carrying the
 * same word, and the dropdown offered every status regardless of where
 * the DPIA actually was — so it could be used to mark a record approved
 * without ever recording the screening decision. The server now says
 * which moves are possible; this only offers those. */
const STATUS_LABELS: Record<string, string> = {
  screening: "Screening",
  not_required: "DPIA not required",
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
  completed: "Completed",
  rejected: "Rejected",
};

export default function DPIADetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: workflow } = useQuery<DpiaWorkflow>({
    queryKey: ["compliance", "dpias", id, "workflow"],
    queryFn: () => apiFetch<DpiaWorkflow>(`/api/v1/compliance/dpias/${id}/workflow`),
  });

  const { data: approvals } = useQuery<Approval[]>({
    queryKey: ["approvals"],
    queryFn: () => apiFetch<Approval[]>("/api/v1/approvals"),
    enabled: workflow?.residual_risk === "high",
  });

  const updateStatus = useMutation({
    mutationFn: (status: DPIAStatus) =>
      apiFetch(`/api/v1/compliance/dpias/${id}/status`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance"] }),
  });

  if (!workflow) return null;

  // §21: while the screening is undecided there is no assessment. Showing
  // four empty Article 35(7) boxes before anybody has said one is needed
  // is what made the old flow feel like a blank form.
  const screeningOnly = workflow.screening_decision === null;
  const notRequired = workflow.status === "not_required";
  const linkedApproval = approvals?.find(
    (a) => a.action_type === `Accept high residual risk: ${workflow.title}`,
  );

  return (
    <div>
      <PageHeader
        title={workflow.title}
        description="Data Protection Impact Assessment — GDPR Article 35."
        actions={
          <StatusBadge
            status={workflow.inherent_risk}
            label={workflow.inherent_risk ? undefined : "Risk not assessed"}
          />
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {workflow.ai_system_id && (
          <Link
            href={`/compliance/ai-systems/${workflow.ai_system_id}`}
            className="text-sm text-[var(--fg-muted)] hover:underline"
          >
            View linked AI system →
          </Link>
        )}
        {workflow.processing_activity_id && (
          <Link
            href="/compliance/privacy/processing-activities"
            className="text-sm text-[var(--fg-muted)] hover:underline"
          >
            View processing activity →
          </Link>
        )}
        <label htmlFor="dpia-status" className="text-sm text-[var(--fg-muted)]">
          Status
        </label>
        {workflow.allowed_transitions.length > 0 ? (
          <select
            id="dpia-status"
            className={selectClassName}
            value={workflow.status}
            onChange={(e) => updateStatus.mutate(e.target.value as DPIAStatus)}
          >
            <option value={workflow.status}>
              {STATUS_LABELS[workflow.status] ?? workflow.status}
            </option>
            {workflow.allowed_transitions.map((next) => (
              <option key={next} value={next}>
                {STATUS_LABELS[next] ?? next}
              </option>
            ))}
          </select>
        ) : (
          // Nowhere to go by hand. Screening leaves through its decision;
          // a completed DPIA does not leave at all.
          <span
            id="dpia-status"
            className="rounded-md border border-[var(--border-default)] px-3 py-1 text-sm text-[var(--fg-default)]"
          >
            {STATUS_LABELS[workflow.status] ?? workflow.status}
          </span>
        )}
        {updateStatus.isError && (
          <span className="text-xs text-[var(--critical-600)]">
            {updateStatus.error instanceof ApiError
              ? updateStatus.error.message
              : "Could not change the status."}
          </span>
        )}
      </div>

      {workflow.quality_review_reason && (
        <Card className="mb-6 border-[var(--warning-500)]/40 bg-[var(--warning-50)]">
          <CardContent className="pt-6">
            <h2 className="mb-1 font-medium text-[var(--warning-800)]">
              Quality review recommended
            </h2>
            <p className="text-sm leading-relaxed text-[var(--warning-700)]">
              {workflow.quality_review_reason}
            </p>
            <p className="mt-2 text-xs text-[var(--warning-700)]">
              The completed record below is unchanged. It says what it said on
              the day it was signed, and rewriting it to satisfy a rule
              introduced afterwards would replace it with a document nobody
              approved.
            </p>
          </CardContent>
        </Card>
      )}

      <DpiaScreeningPanel workflow={workflow} />

      {screeningOnly && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 flex items-center gap-2 font-medium text-[var(--fg-default)]">
              <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
              Waiting on your decision
            </h2>
            <p className="mb-3 text-sm leading-relaxed text-[var(--fg-muted)]">
              There is no assessment yet, and there should not be one until
              somebody decides an assessment is required. Confirm the screening
              to open the DPIA — Veyntra will draft what it can from the
              records this processing already has.
            </p>
            <Link href="/compliance/privacy/dpias">
              <Button size="sm">Go to screening</Button>
            </Link>
          </CardContent>
        </Card>
      )}

      {notRequired && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 font-medium text-[var(--fg-default)]">
              No assessment was carried out
            </h2>
            <p className="text-sm leading-relaxed text-[var(--fg-muted)]">
              The screening above concluded a DPIA is not required for this
              processing, and that screening is the record. Nothing further is
              owed unless the processing changes.
            </p>
          </CardContent>
        </Card>
      )}

      {!screeningOnly && !notRequired && (
        <>
          {/* What the assessment does not know, before anything claims to
              have assessed it. */}
          <DpiaContextGaps
            workflow={workflow}
            readOnly={workflow.status === "completed"}
          />
          <DpiaRiskReview workflow={workflow} />
          {/* The consultation record lives inside the Article 35(7)
              assessment — one record, one place. */}
          <DpiaSections workflow={workflow} />

          {workflow.residual_risk === "high" && (
            <Card className="mb-6">
              <CardContent className="pt-6">
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                  Required Approval
                </h2>
                <p className="mb-2 text-xs text-[var(--fg-subtle)]">
                  A high residual risk remains after mitigation. GDPR Article 36
                  treats that as the case a controller cannot sign off alone, so
                  this DPIA cannot be completed until the approval is granted.
                </p>
                {linkedApproval ? (
                  <div className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
                    <Link href="/approvals" className="hover:underline">
                      {linkedApproval.action_type}
                    </Link>
                    <StatusBadge status={linkedApproval.status} />
                  </div>
                ) : (
                  <Link href="/approvals" className="text-sm hover:underline">
                    Open the Approval Center →
                  </Link>
                )}
              </CardContent>
            </Card>
          )}

          <DpiaCompletion workflow={workflow} />
        </>
      )}
    </div>
  );
}
