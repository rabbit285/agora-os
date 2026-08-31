"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Quote, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { Control, EvidenceSuggestion } from "@/lib/types";

/** Review the mappings the model proposed, and approve or reject each one.
 *
 * Uploading lives in `DocumentLibrary`, immediately above this on the
 * page. There was briefly a second uploader here, which meant two boxes
 * doing the same job with different behaviour — one analysed on upload,
 * the other needed a second click. Reviewing is the job here.
 *
 * The screen is built around the fact that a proposal is *not* evidence.
 * Every card leads with the passage the model quoted and whether that
 * passage was found in the document, because the reviewer's job is to
 * check the citation, not to weigh a confidence score. Confidence is
 * shown last and small: a number a model assigns to its own output is not
 * a measurement, and putting it first would invite people to approve on
 * the strength of it.
 */
export function EvidenceReview() {
  const queryClient = useQueryClient();

  const { data: suggestions } = useQuery<EvidenceSuggestion[]>({
    queryKey: ["compliance", "evidence-suggestions"],
    queryFn: () =>
      apiFetch<EvidenceSuggestion[]>("/api/v1/compliance/evidence/suggestions"),
  });

  const { data: controls } = useQuery<Control[]>({
    queryKey: ["compliance", "controls"],
    queryFn: () => apiFetch<Control[]>("/api/v1/compliance/controls"),
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["compliance", "evidence-suggestions"] });
    void queryClient.invalidateQueries({ queryKey: ["compliance", "evidence"] });
    // The readiness panel is the visible end of this chain, so it has
    // to move when evidence does.
    void queryClient.invalidateQueries({ queryKey: ["compliance", "overview"] });
  };

  const approve = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/compliance/evidence/suggestions/${id}/approve`, {
        method: "POST",
        body: {},
      }),
    onSuccess: refresh,
  });

  const reject = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/compliance/evidence/suggestions/${id}/reject`, { method: "POST" }),
    onSuccess: refresh,
  });

  const controlTitle = (id: string) =>
    controls?.find((c) => c.id === id)?.title ?? "Unknown control";

  const pending = (suggestions ?? []).filter((s) => s.status === "proposed");
  const unverifiable = (suggestions ?? []).filter((s) => s.status === "unverifiable");
  const error = approve.error ?? reject.error;

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Evidence awaiting your review
      </h2>

      {error && (
        <p className="mb-3 text-sm text-[var(--critical-600)]">
          {error instanceof ApiError ? error.message : (error as Error).message}
        </p>
      )}

      {pending.length === 0 && unverifiable.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">
          No proposals awaiting review. Upload a document above and Veyntra will propose which
          controls it evidences.
        </p>
      )}

      <div className="flex flex-col gap-3">
        {pending.map((suggestion) => (
          <Card key={suggestion.id}>
            <CardContent className="pt-6">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-[var(--fg-default)]">
                  {controlTitle(suggestion.control_id)}
                </span>
                <Badge variant="success" className="gap-1">
                  <Check className="h-3 w-3" aria-hidden="true" />
                  Quote found in document
                </Badge>
              </div>

              {suggestion.rationale && (
                <p className="mb-3 text-sm leading-relaxed text-[var(--fg-muted)]">
                  {suggestion.rationale}
                </p>
              )}

              {/* The passage leads, because checking it is the review. */}
              <blockquote className="mb-3 flex gap-2 border-l-2 border-[var(--brand-primary)] bg-[var(--bg-app)] p-3">
                <Quote
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--fg-subtle)]"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-sm italic leading-relaxed text-[var(--fg-default)]">
                    {suggestion.quoted_passage}
                  </p>
                  {/* Where to look. Without it, checking a citation means
                      re-reading the whole document. */}
                  {suggestion.source_location && (
                    <p className="mt-1.5 text-xs text-[var(--fg-subtle)]">
                      {suggestion.source_location}
                      {suggestion.evidence_type
                        ? ` · ${suggestion.evidence_type.replace(/_/g, " ")}`
                        : ""}
                    </p>
                  )}
                </div>
              </blockquote>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  disabled={approve.isPending}
                  onClick={() => approve.mutate(suggestion.id)}
                >
                  <Check className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                  Approve as evidence
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={reject.isPending}
                  onClick={() => reject.mutate(suggestion.id)}
                >
                  <X className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                  Reject
                </Button>
                {suggestion.confidence !== null && (
                  <span className="text-xs text-[var(--fg-subtle)]">
                    model confidence {Math.round(suggestion.confidence * 100)}%
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        ))}

        {unverifiable.map((suggestion) => (
          <Card key={suggestion.id} className="border-[var(--warning-500)]/35">
            <CardContent className="pt-6">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-[var(--fg-default)]">
                  {controlTitle(suggestion.control_id)}
                </span>
                <Badge variant="destructive" className="gap-1">
                  <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                  Quote not found in document
                </Badge>
              </div>
              <p className="text-sm leading-relaxed text-[var(--warning-700)]">
                This proposal quoted a passage that does not appear in the uploaded document, so
                it cannot be approved. It is kept here so the behaviour is visible rather than
                hidden — attach the document by hand if it is genuinely relevant.
              </p>
              {suggestion.quoted_passage && (
                <blockquote className="mt-2 border-l-2 border-[var(--warning-500)]/50 p-3 text-sm italic text-[var(--fg-muted)]">
                  {suggestion.quoted_passage}
                </blockquote>
              )}
              <div className="mt-3">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={reject.isPending}
                  onClick={() => reject.mutate(suggestion.id)}
                >
                  Dismiss
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
