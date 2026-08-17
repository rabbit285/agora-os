"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Quote, Sparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { uploadFile } from "@/lib/upload";
import type { Control, EvidenceSuggestion } from "@/lib/types";

/** Upload a document, let the model propose where it belongs, approve or
 * reject each proposal.
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [lastRun, setLastRun] = useState<{
    controls_considered: number;
    unverifiable_count: number;
  } | null>(null);

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
  };

  const analyze = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a document first.");
      const fileId = await uploadFile(file, { classification: "confidential" });
      return apiFetch<{
        suggestions: EvidenceSuggestion[];
        controls_considered: number;
        unverifiable_count: number;
      }>("/api/v1/compliance/evidence/analyze", {
        method: "POST",
        body: { file_id: fileId },
      });
    },
    onSuccess: (data) => {
      setLastRun({
        controls_considered: data.controls_considered,
        unverifiable_count: data.unverifiable_count,
      });
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      refresh();
    },
  });

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
  const error = analyze.error ?? approve.error ?? reject.error;

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Document intelligence
      </h2>

      <Card className="mb-4">
        <CardContent className="pt-6">
          <p className="mb-3 text-sm leading-relaxed text-[var(--fg-muted)]">
            Upload a policy or procedure and Veyntra will read it against your controls and
            propose where it belongs. Proposals are not evidence — nothing reaches your
            compliance status until you approve it.
          </p>

          <div className="flex flex-col gap-2">
            <input
              ref={fileInputRef}
              type="file"
              className="text-sm text-[var(--fg-muted)] file:mr-3 file:rounded-[var(--radius-md)] file:border file:border-[var(--border-default)] file:bg-[var(--bg-surface)] file:px-3 file:py-1.5 file:text-sm file:text-[var(--fg-default)]"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <div>
              <Button disabled={!file || analyze.isPending} onClick={() => analyze.mutate()}>
                <Sparkles className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                {analyze.isPending ? "Reading the document…" : "Analyze for evidence"}
              </Button>
            </div>
          </div>

          {lastRun && (
            <p className="mt-3 text-xs text-[var(--fg-subtle)]">
              Checked against {lastRun.controls_considered} control
              {lastRun.controls_considered === 1 ? "" : "s"}.
              {lastRun.unverifiable_count > 0 && (
                <>
                  {" "}
                  {lastRun.unverifiable_count} proposal
                  {lastRun.unverifiable_count === 1 ? " was" : "s were"} discarded because the
                  quoted passage could not be found in the document.
                </>
              )}
            </p>
          )}

          {error && (
            <p className="mt-3 text-sm text-[var(--critical-600)]">
              {error instanceof ApiError ? error.message : (error as Error).message}
            </p>
          )}
        </CardContent>
      </Card>

      {pending.length === 0 && unverifiable.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No proposals awaiting review.</p>
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
                <p className="text-sm italic leading-relaxed text-[var(--fg-default)]">
                  {suggestion.quoted_passage}
                </p>
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
