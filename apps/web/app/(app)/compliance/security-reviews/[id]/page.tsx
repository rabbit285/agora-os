"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Download } from "lucide-react";

import { ExportReview } from "@/components/compliance/export-review";
import { LifecycleMenu } from "@/components/compliance/lifecycle-menu";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  ReviewExportRecord,
  SecurityReviewDetail,
  SecurityReviewSyncResult,
} from "@/lib/types";

/** One customer's security review: the engagement, and what is in it.
 *
 * This page used to be the sales view — an opportunity title, a deal
 * blocker flag, and exactly one questionnaire. The opportunity is gone
 * and a review holds as many questionnaires as the customer sends, so
 * what it shows now is the conversation: who is asking, how far the
 * answers have got across all of it, and whether the engagement is still
 * open.
 *
 * The legacy fields are still rendered when a row carries them. Reviews
 * created before the change have a gap count and an opportunity, and
 * their page should keep working rather than losing the record.
 */
function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function SecurityReviewDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: review } = useQuery<SecurityReviewDetail>({
    queryKey: ["compliance", "security-reviews", id],
    queryFn: () =>
      apiFetch<SecurityReviewDetail>(
        `/api/v1/compliance/security-reviews/${id}`,
      ),
  });

  // Legacy actions, kept for rows that came from the sales flow.
  const sync = useMutation({
    mutationFn: () =>
      apiFetch<SecurityReviewSyncResult>(
        `/api/v1/compliance/security-reviews/${id}/sync`,
        { method: "POST" },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["compliance", "security-reviews", id],
      });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  if (!review) return null;

  const { progress } = review;
  const archived = review.archived_at !== null;
  const title = review.title ?? review.opportunity_title ?? "Customer security review";

  return (
    <div>
      <PageHeader
        title={title}
        description={
          review.customer_name
            ? `Security review for ${review.customer_name}`
            : "Customer security review"
        }
        actions={
          <div className="flex items-center gap-2">
            {/* How far it got, and whether it is still open. Both, and
                separately: "Ready to share" and "Archived" together is
                what a finished engagement looks like. */}
            {archived && (
              <Badge variant="secondary" className="gap-1">
                <Archive className="h-3 w-3" aria-hidden="true" />
                Archived {review.archived_at ? formatDate(review.archived_at) : ""}
              </Badge>
            )}
            <StatusBadge status={review.status} />
            <ExportReview
              reviewId={review.id}
              reviewStatus={review.status}
              archived={archived}
            />
            <LifecycleMenu
              kind="security_review"
              id={review.id}
              title={title}
              canDelete={false}
              deleteBlockedReason="A customer security review is kept as history."
              archived={archived}
            />
          </div>
        }
      />

      {/* The engagement's work, added up across every questionnaire in
          it — the server's numbers, so this page and the card on
          Assessments cannot disagree. */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm text-[var(--fg-muted)]">
              <span className="text-lg font-semibold text-[var(--fg-default)]">
                {progress.approved}
              </span>{" "}
              of {progress.total} approved across {progress.questionnaires}{" "}
              questionnaire{progress.questionnaires === 1 ? "" : "s"}
            </p>
            <p className="text-sm text-[var(--fg-muted)]">
              {progress.percent_complete}% complete
            </p>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--bg-subtle)]">
            <div
              className="h-full rounded-full bg-[var(--success-600)]"
              style={{ width: `${progress.percent_complete}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-[var(--fg-subtle)]">
            {progress.needs_review} need review · {progress.draft} drafted ·{" "}
            {progress.unanswered} unanswered
          </p>
        </CardContent>
      </Card>

      {/* Only where a row actually carries them. */}
      {(review.gap_count > 0 || review.approval_id) && (
        <div className="mb-6 flex flex-wrap items-center gap-4">
          {review.gap_count > 0 && (
            <span className="text-sm text-[var(--fg-muted)]">
              {review.gap_count} open gap{review.gap_count === 1 ? "" : "s"}
            </span>
          )}
          {review.approval_id && (
            <span className="text-sm text-[var(--fg-muted)]">
              Approval: {review.approval_status ?? "pending"}
            </span>
          )}
          {review.opportunity_id && (
            <Button
              variant="outline"
              size="sm"
              disabled={sync.isPending}
              onClick={() => sync.mutate()}
            >
              Sync answers &amp; evidence
            </Button>
          )}
        </div>
      )}
      {sync.isError && (
        <p className="mb-4 text-sm text-[var(--critical-600)]">
          {sync.error instanceof ApiError
            ? sync.error.message
            : "Could not sync this review."}
        </p>
      )}

      <GeneratedOutputs reviewId={review.id} />

      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Questionnaires in this review
      </h2>

      {review.questionnaires.length === 0 ? (
        <EmptyState
          title="No questionnaires in this review yet"
          description="Create a questionnaire marked customer-provided and name this customer — it joins this review automatically."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {review.questionnaires.map((row) => (
            <Link key={row.id} href={row.href}>
              <Card className="transition-colors hover:border-[var(--border-strong)]">
                <CardContent className="flex items-center justify-between gap-4 pt-6">
                  <div className="min-w-0">
                    <div className="font-medium text-[var(--fg-default)]">
                      {row.title}
                    </div>
                    <div className="text-xs text-[var(--fg-subtle)]">
                      {row.progress.total} question
                      {row.progress.total === 1 ? "" : "s"}
                      {row.progress.total > 0 && (
                        <>
                          {" · "}
                          {row.progress.approved}/{row.progress.total} approved
                        </>
                      )}
                      {row.archived_at && (
                        <> · Archived {formatDate(row.archived_at)}</>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {row.archived_at && (
                      <Badge variant="secondary" className="gap-1">
                        <Archive className="h-3 w-3" aria-hidden="true" />
                        Archived
                      </Badge>
                    )}
                    <StatusBadge status={row.status} />
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

/** The packages already generated for this review.
 *
 * Nothing here is ever replaced. Regenerating adds a version and the
 * earlier one stays downloadable, because the customer still has their
 * copy and our record of what we sent them has to match it.
 */
function GeneratedOutputs({ reviewId }: { reviewId: string }) {
  const { data: exports } = useQuery<ReviewExportRecord[]>({
    queryKey: ["compliance", "security-reviews", reviewId, "exports"],
    queryFn: () =>
      apiFetch<ReviewExportRecord[]>(
        `/api/v1/compliance/security-reviews/${reviewId}/exports`,
      ),
  });

  if (!exports || exports.length === 0) return null;

  return (
    <section className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Generated outputs
      </h2>
      <div className="flex flex-col gap-2">
        {exports.map((record) => (
          <GeneratedOutputRow key={record.id} reviewId={reviewId} record={record} />
        ))}
      </div>
    </section>
  );
}

function GeneratedOutputRow({
  reviewId,
  record,
}: {
  reviewId: string;
  record: ReviewExportRecord;
}) {
  const [error, setError] = useState<string | null>(null);

  const download = useMutation({
    mutationFn: () =>
      apiFetch<{ url: string; filename: string }>(
        `/api/v1/compliance/security-reviews/${reviewId}/exports/${record.id}/download`,
      ),
    onMutate: () => setError(null),
    onSuccess: (result) => window.open(result.url, "_blank", "noopener"),
    onError: () => setError("Could not prepare the download."),
  });

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-6">
        <div className="min-w-0">
          <div className="font-medium text-[var(--fg-default)]">
            {record.output_label} · v{record.version}
          </div>
          <div className="text-xs text-[var(--fg-subtle)]">
            {record.file_format.toUpperCase()} · Generated{" "}
            {formatDate(record.generated_at)} · {record.answer_count} response
            {record.answer_count === 1 ? "" : "s"}
            {record.document_count > 0 &&
              ` · ${record.document_count} document${
                record.document_count === 1 ? "" : "s"
              }`}
            {/* §27: generated and shared are different facts. */}
            {record.shared_at
              ? ` · Shared ${formatDate(record.shared_at)}`
              : " · Not yet shared"}
          </div>
          {/* §21: the old package is unchanged. This only says a newer
              one can be produced. */}
          {record.stale && (
            <div className="mt-1 text-xs text-[var(--warning-700)]">
              The review has changed since this was generated.
            </div>
          )}
          {error && (
            <p role="alert" className="mt-1 text-xs text-[var(--fg-danger)]">
              {error}
            </p>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={!record.file_id || download.isPending}
          onClick={() => download.mutate()}
        >
          <Download className="mr-2 h-4 w-4" aria-hidden="true" />
          Download
        </Button>
      </CardContent>
    </Card>
  );
}
