"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleDashed, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { VendorAssessment, VendorDetail } from "@/lib/types";

const OUTCOME: Record<string, { variant: "success" | "destructive" | "secondary"; icon: typeof CheckCircle2 }> = {
  satisfied: { variant: "success", icon: CheckCircle2 },
  missing: { variant: "destructive", icon: AlertTriangle },
  unanswered: { variant: "secondary", icon: CircleDashed },
};

const APPROVAL_LABEL: Record<string, { label: string; variant: "success" | "secondary" | "destructive" | "outline" }> = {
  not_submitted: { label: "Not submitted", variant: "outline" },
  pending: { label: "Pending review", variant: "secondary" },
  approved: { label: "Approved", variant: "success" },
  // Deliberately not styled as success. A conditional approval is a
  // qualified yes, and showing it in the same colour as a clean approval
  // is how the caveat gets lost.
  conditionally_approved: { label: "Conditionally approved", variant: "secondary" },
  rejected: { label: "Rejected", variant: "destructive" },
};

export function VendorReview({ vendor }: { vendor: VendorDetail }) {
  const queryClient = useQueryClient();
  const [conditions, setConditions] = useState(vendor.approval_conditions ?? "");

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["compliance", "vendors", vendor.id] });

  const review = useMutation({
    mutationFn: (kind: "privacy" | "security") =>
      apiFetch<VendorAssessment>(`/api/v1/compliance/vendors/${vendor.id}/${kind}-review`, {
        method: "POST",
      }),
    onSuccess: invalidate,
  });

  const decide = useMutation({
    mutationFn: (decision: string) =>
      apiFetch(`/api/v1/compliance/vendors/${vendor.id}/approval`, {
        method: "POST",
        body: { decision, conditions: conditions || null },
      }),
    onSuccess: invalidate,
  });

  // Newest of each type: a privacy review and a security review are
  // separate positions and neither supersedes the other.
  const latest = (type: string) =>
    vendor.assessments
      .filter((a) => a.assessment_type === type)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];

  const approval = APPROVAL_LABEL[vendor.approval_state] ?? APPROVAL_LABEL.not_submitted;
  const error = review.error ?? decide.error;

  return (
    <>
      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <ReviewPanel
          title="Privacy review"
          assessment={latest("privacy")}
          pending={review.isPending}
          onRun={() => review.mutate("privacy")}
        />
        <ReviewPanel
          title="Security review"
          assessment={latest("security")}
          pending={review.isPending}
          onRun={() => review.mutate("security")}
        />
      </div>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-medium text-[var(--fg-default)]">Approval decision</h2>
            <Badge variant={approval.variant}>{approval.label}</Badge>
          </div>

          {vendor.approval_state === "conditionally_approved" && vendor.approval_conditions && (
            <div className="mb-4 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--warning-700)]">
                Conditions
              </p>
              <p className="mt-1 text-sm leading-relaxed text-[var(--warning-700)]">
                {vendor.approval_conditions}
              </p>
            </div>
          )}

          <label className="mb-3 flex flex-col gap-1 text-sm">
            <span className="text-[var(--fg-default)]">
              Conditions (required for a conditional approval)
            </span>
            <textarea
              rows={2}
              className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 text-sm text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
              placeholder="What is permitted, and what must be completed before full approval"
              value={conditions}
              onChange={(e) => setConditions(e.target.value)}
            />
          </label>

          {error && (
            <p className="mb-3 text-sm text-[var(--critical-600)]">
              {error instanceof ApiError ? error.message : "Something went wrong."}
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={decide.isPending} onClick={() => decide.mutate("approved")}>
              Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={decide.isPending || !conditions.trim()}
              onClick={() => decide.mutate("conditionally_approved")}
            >
              Approve with conditions
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={decide.isPending}
              onClick={() => decide.mutate("rejected")}
            >
              Reject
            </Button>
          </div>

          {vendor.approval_decided_at && (
            <p className="mt-3 text-xs text-[var(--fg-subtle)]">
              Decided {new Date(vendor.approval_decided_at).toLocaleString()}
            </p>
          )}
        </CardContent>
      </Card>
    </>
  );
}

function ReviewPanel({
  title,
  assessment,
  pending,
  onRun,
}: {
  title: string;
  assessment: VendorAssessment | undefined;
  pending: boolean;
  onRun: () => void;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-medium text-[var(--fg-default)]">{title}</h2>
          <Button size="sm" variant="outline" disabled={pending} onClick={onRun}>
            {assessment ? "Re-run" : "Run review"}
          </Button>
        </div>

        {assessment ? (
          <>
            <div className="mb-3 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-[var(--fg-subtle)]" aria-hidden="true" />
              <Badge
                variant={
                  assessment.risk_conclusion === "low"
                    ? "success"
                    : assessment.risk_conclusion === "medium"
                      ? "secondary"
                      : "destructive"
                }
              >
                {assessment.risk_conclusion} risk
              </Badge>
              <span className="text-sm text-[var(--fg-muted)]">{assessment.notes}</span>
            </div>

            <ul className="flex flex-col gap-2">
              {(assessment.findings?.checks ?? []).map((check) => {
                const presentation = OUTCOME[check.outcome] ?? OUTCOME.unanswered;
                return (
                  <li key={check.check} className="flex items-start gap-2">
                    <presentation.icon
                      className={`mt-0.5 h-4 w-4 shrink-0 ${
                        check.outcome === "satisfied"
                          ? "text-[var(--success-600)]"
                          : check.outcome === "missing"
                            ? "text-[var(--critical-600)]"
                            : "text-[var(--warning-700)]"
                      }`}
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-sm font-medium text-[var(--fg-default)]">{check.check}</p>
                      <p className="text-xs leading-relaxed text-[var(--fg-muted)]">
                        {check.detail}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>

            {assessment.findings?.coverage_note && (
              <p className="mt-3 text-xs leading-relaxed text-[var(--fg-subtle)]">
                {assessment.findings.coverage_note}
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-[var(--fg-muted)]">
            This review has not been run for this vendor.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
