"use client";

import Link from "next/link";
import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { SecurityReviewDetail, SecurityReviewSyncResult } from "@/lib/types";

export default function SecurityReviewDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: review } = useQuery<SecurityReviewDetail>({
    queryKey: ["compliance", "security-reviews", id],
    queryFn: () => apiFetch<SecurityReviewDetail>(`/api/v1/compliance/security-reviews/${id}`),
  });

  const sync = useMutation({
    mutationFn: () =>
      apiFetch<SecurityReviewSyncResult>(`/api/v1/compliance/security-reviews/${id}/sync`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["compliance", "security-reviews", id] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const clear = useMutation({
    mutationFn: () =>
      apiFetch<SecurityReviewDetail>(`/api/v1/compliance/security-reviews/${id}/clear`, {
        method: "POST",
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "security-reviews", id] }),
  });

  if (!review) return null;

  return (
    <div>
      <PageHeader
        title={review.opportunity_title}
        description="Enterprise Sales Security Review"
        actions={<StatusBadge status={review.status} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {review.is_deal_blocker && (
          <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800">
            Deal blocker
          </span>
        )}
        <span className="text-sm text-neutral-500">
          {review.gap_count} open gap{review.gap_count === 1 ? "" : "s"}
        </span>
        {review.approval_id && (
          <span className="text-sm text-neutral-500">
            Approval: {review.approval_status ?? "pending"}
          </span>
        )}
        {review.trust_package_file_id && (
          <span className="text-sm text-emerald-600">Trust package generated</span>
        )}
      </div>

      <div className="mb-8 flex flex-wrap gap-2">
        <Button variant="outline" disabled={sync.isPending} onClick={() => sync.mutate()}>
          Sync answers &amp; evidence
        </Button>
        <Button
          disabled={clear.isPending || review.status === "cleared"}
          onClick={() => clear.mutate()}
        >
          Clear review
        </Button>
      </div>
      {sync.isSuccess && (
        <p className="mb-4 text-sm text-neutral-500">
          {sync.data.tasks_created} remediation task{sync.data.tasks_created === 1 ? "" : "s"}{" "}
          created. {sync.data.review.gap_count} gap{sync.data.review.gap_count === 1 ? "" : "s"}{" "}
          remain.
        </p>
      )}
      {clear.isError && (
        <p className="mb-4 text-sm text-red-600">
          {clear.error instanceof ApiError ? clear.error.message : "Could not clear review."}
        </p>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Questionnaire
        </h2>
        <Link href={`/compliance/questionnaires/${review.questionnaire.id}`}>
          <Card className="transition-colors hover:border-neutral-400">
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">{review.questionnaire.title}</div>
                <div className="text-xs text-neutral-400">
                  {review.questionnaire.questions.length} question
                  {review.questionnaire.questions.length === 1 ? "" : "s"}
                </div>
              </div>
              <StatusBadge status={review.questionnaire.status} />
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  );
}
