"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { DsarResponsePreview, DsarSourceLine, DsarWorkflowState } from "@/lib/types";

function SourceBlock({
  title,
  rows,
  empty,
}: {
  title: string;
  rows: DsarSourceLine[];
  empty: string;
}) {
  return (
    <div className="mb-3">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
        {title}
      </p>
      {rows.length === 0 ? (
        <p className="text-sm text-[var(--fg-muted)]">{empty}</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {rows.map((row) => (
            <li key={row.name} className="text-sm text-[var(--fg-default)]">
              {row.name} — <span className="text-[var(--fg-muted)]">{row.state_label}</span>
              {row.decision_reason && (
                <span className="block text-xs text-[var(--fg-subtle)]">
                  {row.decision_reason}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Draft, preview, approve, send — in that order, with no shortcuts.
 *
 * The approval is of a specific text. The digest travels with it, and
 * the server refuses if the request moved in between, because otherwise
 * the answer could change between the moment somebody read it and the
 * moment it went out — and the thing that changed would be a person's
 * personal data.
 */
export function DsarResponsePackagePanel({
  dsarId,
  workflow,
}: {
  dsarId: string;
  workflow: DsarWorkflowState | undefined;
}) {
  const queryClient = useQueryClient();
  const [letter, setLetter] = useState<string | null>(null);

  const { data: preview } = useQuery<DsarResponsePreview>({
    queryKey: ["compliance", "dsars", dsarId, "response-preview"],
    queryFn: () =>
      apiFetch<DsarResponsePreview>(`/api/v1/compliance/dsars/${dsarId}/response/preview`),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["compliance", "dsars", dsarId] });

  const approve = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dsars/${dsarId}/response/approve`, {
        method: "POST",
        body: { digest: preview!.digest, letter: letter ?? undefined },
      }),
    onSuccess: invalidate,
  });

  const markSent = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dsars/${dsarId}/response/sent`, { method: "POST" }),
    onSuccess: invalidate,
  });

  if (!preview) return null;

  // The drafted letter until somebody edits it, then theirs. Derived
  // rather than copied into state on load: seeding from an effect would
  // discard whatever they were typing on the next refetch.
  const letterValue = letter ?? preview.letter;

  const status = workflow?.package_status ?? null;
  const approved = status === "approved" || status === "sent";
  const error = approve.error ?? markSent.error;

  return (
    <Card className="mb-6" id="package">
      <CardContent className="pt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
            <h2 className="font-medium text-[var(--fg-default)]">Response package</h2>
          </div>
          {status && <Badge variant="outline">{status}</Badge>}
        </div>

        {preview.blockers.length > 0 && (
          <ul className="mb-3 space-y-1 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] p-3">
            {preview.blockers.map((blocker) => (
              <li key={blocker} className="text-sm text-[var(--fg-muted)]">
                {blocker}
              </li>
            ))}
          </ul>
        )}

        <div className="mb-4 grid gap-x-6 sm:grid-cols-2">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
              Identity verification
            </p>
            <p className="text-sm text-[var(--fg-default)]">
              {preview.identity_method ?? "Not recorded"}
            </p>
            {preview.identity_notes && (
              <p className="text-xs text-[var(--fg-muted)]">{preview.identity_notes}</p>
            )}
            {preview.identity_verified_by && (
              <p className="text-xs text-[var(--fg-subtle)]">
                Verified by {preview.identity_verified_by}
              </p>
            )}
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
              Deadline
            </p>
            <p className="text-sm text-[var(--fg-default)]">
              {new Date(preview.due_at).toLocaleDateString()}
            </p>
          </div>
        </div>

        {preview.coverage && (
          <div
            className={`mb-4 rounded-[var(--radius-md)] border p-3 ${
              preview.coverage.complete
                ? "border-[var(--border-default)] bg-[var(--bg-app)]"
                : "border-[var(--warning-300)] bg-[var(--warning-50)]"
            }`}
            data-testid="coverage"
          >
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
              Search coverage
            </p>
            <dl className="mt-1 grid gap-x-6 gap-y-0.5 text-sm sm:grid-cols-2">
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--fg-muted)]">Search scope confirmed</dt>
                <dd className="text-[var(--fg-default)]">{preview.coverage.scope_confirmed}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--fg-muted)]">Automatically searched</dt>
                <dd className="text-[var(--fg-default)]">
                  {preview.coverage.automatically_searched}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--fg-muted)]">Manual sources completed</dt>
                <dd className="text-[var(--fg-default)]">{preview.coverage.manual_completed}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--fg-muted)]">Outstanding</dt>
                <dd className="text-[var(--fg-default)]">{preview.coverage.outstanding}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--fg-muted)]">Searched with no matches</dt>
                <dd className="text-[var(--fg-default)]">
                  {preview.coverage.searched_no_matches}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--fg-muted)]">Records found</dt>
                <dd className="text-[var(--fg-default)]">{preview.coverage.records_found}</dd>
              </div>
            </dl>
            {!preview.coverage.complete && (
              /* Said outright rather than left to be inferred from the
                 numbers above it. */
              <p className="mt-2 text-xs leading-relaxed text-[var(--fg-muted)]">
                This response is partial: some sources in scope have not been searched.
              </p>
            )}
          </div>
        )}

        <SourceBlock title="Included" rows={preview.included} empty="None." />
        <SourceBlock title="Redacted" rows={preview.redacted} empty="None." />
        <SourceBlock title="Excluded" rows={preview.excluded} empty="None." />
        {/* Named in the requester's copy, not only internally: the
            difference between "we found nothing" and "we did not look"
            is theirs to know. */}
        <SourceBlock
          title="Not searched — follow-up required"
          rows={preview.not_searched}
          empty="None."
        />

        <p className="mt-4 text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
          Response letter
        </p>
        <textarea
          className="mt-1 min-h-[220px] w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-white p-3 font-mono text-xs leading-relaxed text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          value={letterValue}
          readOnly={approved}
          aria-label="Response letter"
          onChange={(event) => setLetter(event.target.value)}
        />

        {error && (
          <p className="mt-3 text-sm text-[var(--critical-600)]">
            {error instanceof ApiError ? error.message : "Something went wrong."}
          </p>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {!approved ? (
            <Button
              size="sm"
              disabled={approve.isPending || preview.blockers.length > 0}
              onClick={() => approve.mutate()}
            >
              {approve.isPending ? "Approving…" : "Approve response"}
            </Button>
          ) : (
            <>
              <span className="text-sm text-[var(--fg-muted)]">
                Approved. What you read above is exactly what will be sent.
              </span>
              {status !== "sent" && (
                <Button
                  size="sm"
                  disabled={markSent.isPending}
                  onClick={() => markSent.mutate()}
                >
                  <Send className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                  Mark response sent
                </Button>
              )}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
