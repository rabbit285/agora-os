"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  FileSpreadsheet,
  FileText,
  Package,
  TriangleAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  ExportOutputType,
  ExportPreview,
  ReviewExportRecord,
} from "@/lib/types";

/** Choosing, inspecting and then generating a customer package.
 *
 * The two steps are the feature. Clicking Export must not produce a file:
 * the compliance team has to see exactly what would go to the customer —
 * which answers, which documents, which limitations — while it is still
 * only data on a screen. Only then does anything become sendable.
 *
 * The preview is a read. Opening it, changing the selection and closing
 * it leaves nothing behind, so the generated-outputs history means "what
 * we sent" rather than "what somebody considered sending".
 */
const OUTPUTS: {
  key: ExportOutputType;
  label: string;
  description: string;
  icon: typeof FileText;
}[] = [
  {
    key: "summary",
    label: "Security Review Summary",
    description:
      "A PDF report: the approved responses, the evidence behind them, and any limitations they record.",
    icon: FileText,
  },
  {
    key: "questionnaire",
    label: "Completed questionnaire",
    description:
      "The customer's questions with the approved answers, as a spreadsheet.",
    icon: FileSpreadsheet,
  },
  {
    key: "evidence_pack",
    label: "Evidence / Assurance Pack",
    description:
      "A ZIP containing the summary, the completed questionnaire, and the documents cleared for sharing.",
    icon: Package,
  },
];

export function ExportReview({
  reviewId,
  reviewStatus,
  archived,
}: {
  reviewId: string;
  reviewStatus: string;
  archived: boolean;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [output, setOutput] = useState<ExportOutputType | null>(null);
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [title, setTitle] = useState("");
  const [introduction, setIntroduction] = useState("");
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setOutput(null);
    setPreview(null);
    setTitle("");
    setIntroduction("");
    setExcluded(new Set());
    setError(null);
  };

  const prepare = useMutation<ExportPreview, unknown, ExportOutputType>({
    mutationFn: (outputType) =>
      apiFetch<ExportPreview>(
        `/api/v1/compliance/security-reviews/${reviewId}/export/preview`,
        { method: "POST", body: { output_type: outputType } },
      ),
    onMutate: () => setError(null),
    onSuccess: (result) => {
      setPreview(result);
      setTitle(result.title);
      setIntroduction(result.introduction ?? "");
      setExcluded(new Set());
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Could not prepare the preview.",
      ),
  });

  // Re-previewing after a selection change. The server decides what is
  // eligible every time, so removing a document here can never smuggle
  // an ineligible one back in.
  const refresh = useMutation<ExportPreview, unknown, string[]>({
    mutationFn: (include) =>
      apiFetch<ExportPreview>(
        `/api/v1/compliance/security-reviews/${reviewId}/export/preview`,
        {
          method: "POST",
          body: {
            output_type: output,
            include_documents: include,
            title: title.trim() || null,
            introduction: introduction.trim() || null,
          },
        },
      ),
    onSuccess: (result) => setPreview(result),
  });

  const generate = useMutation<ReviewExportRecord, unknown, void>({
    mutationFn: () =>
      apiFetch<ReviewExportRecord>(
        `/api/v1/compliance/security-reviews/${reviewId}/export`,
        {
          method: "POST",
          body: {
            output_type: output,
            include_documents: preview?.documents
              .filter((d) => d.included)
              .map((d) => d.file_id),
            title: title.trim() || null,
            introduction: introduction.trim() || null,
            confirm_digest: preview?.digest,
          },
        },
      ),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setOpen(false);
      reset();
      await queryClient.invalidateQueries({ queryKey: ["compliance"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was generated.",
      ),
  });

  const toggleDocument = (fileId: string, include: boolean) => {
    const next = new Set(excluded);
    if (include) next.delete(fileId);
    else next.add(fileId);
    setExcluded(next);
    const keep = (preview?.documents ?? [])
      .filter((d) => d.eligible && !next.has(d.file_id))
      .map((d) => d.file_id);
    refresh.mutate(keep);
  };

  return (
    <>
      <Button
        size="sm"
        variant={reviewStatus === "ready_to_share" ? "default" : "outline"}
        onClick={() => setOpen(true)}
      >
        <Download className="mr-2 h-4 w-4" aria-hidden="true" />
        Export / Share
      </Button>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          // §29: closing leaves nothing behind. Nothing was created.
          if (!next) reset();
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
          {preview === null ? (
            <>
              <DialogHeader>
                <DialogTitle>Prepare customer package</DialogTitle>
                <DialogDescription>
                  Choose what to produce. Nothing is generated until you have
                  seen exactly what it would contain.
                </DialogDescription>
              </DialogHeader>

              <div className="flex flex-col gap-2">
                {OUTPUTS.map((entry) => {
                  const Icon = entry.icon;
                  return (
                    <button
                      key={entry.key}
                      type="button"
                      onClick={() => setOutput(entry.key)}
                      aria-pressed={output === entry.key}
                      className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors ${
                        output === entry.key
                          ? "border-[var(--brand-primary)] bg-[var(--bg-subtle)]"
                          : "border-[var(--border-default)] hover:border-[var(--border-strong)]"
                      }`}
                    >
                      <Icon
                        className="mt-0.5 h-4 w-4 shrink-0 text-[var(--fg-muted)]"
                        aria-hidden="true"
                      />
                      <span className="min-w-0">
                        <span className="block font-medium text-[var(--fg-default)]">
                          {entry.label}
                        </span>
                        <span className="block text-sm text-[var(--fg-muted)]">
                          {entry.description}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>

              {error && (
                <p role="alert" className="text-sm text-[var(--fg-danger)]">
                  {error}
                </p>
              )}

              <DialogFooter className="border-t border-[var(--border-default)] pt-4">
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button
                  disabled={!output || prepare.isPending}
                  onClick={() => output && prepare.mutate(output)}
                >
                  {prepare.isPending ? "Preparing…" : "Continue to preview"}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <PreviewStep
              preview={preview}
              title={title}
              setTitle={setTitle}
              introduction={introduction}
              setIntroduction={setIntroduction}
              onToggleDocument={toggleDocument}
              onBack={() => setPreview(null)}
              onGenerate={() => generate.mutate()}
              generating={generate.isPending}
              archived={archived}
              error={error}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function PreviewStep({
  preview,
  title,
  setTitle,
  introduction,
  setIntroduction,
  onToggleDocument,
  onBack,
  onGenerate,
  generating,
  archived,
  error,
}: {
  preview: ExportPreview;
  title: string;
  setTitle: (value: string) => void;
  introduction: string;
  setIntroduction: (value: string) => void;
  onToggleDocument: (fileId: string, include: boolean) => void;
  onBack: () => void;
  onGenerate: () => void;
  generating: boolean;
  archived: boolean;
  error: string | null;
}) {
  const format = preview.file_format.toUpperCase();
  return (
    <>
      <DialogHeader>
        <DialogTitle>
          Preview — {preview.output_label}
        </DialogTitle>
        <DialogDescription>
          This is what the customer would receive. Nothing has been generated
          yet.
        </DialogDescription>
      </DialogHeader>

      {archived && (
        <p className="rounded-md bg-[var(--bg-subtle)] px-3 py-2 text-sm text-[var(--fg-muted)]">
          This review is archived. You are generating from its historical
          state.
        </p>
      )}

      {preview.blockers.length > 0 && (
        <div className="rounded-lg border border-[var(--warning-300)] bg-[var(--warning-50)] px-4 py-3">
          <div className="flex items-start gap-2">
            <TriangleAlert
              className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-700)]"
              aria-hidden="true"
            />
            <div>
              <p className="text-sm font-medium text-[var(--fg-default)]">
                Cannot export final review yet
              </p>
              <ul className="mt-1 list-inside list-disc text-sm text-[var(--fg-muted)]">
                {preview.blockers.map((blocker) => (
                  <li key={blocker.code}>{blocker.message}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-4">
        <div>
          <label
            htmlFor="export-title"
            className="mb-1.5 block text-xs font-medium text-[var(--fg-muted)]"
          >
            Report title
          </label>
          <Input
            id="export-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>

        {preview.output_type === "summary" && (
          <div>
            <label
              htmlFor="export-intro"
              className="mb-1.5 block text-xs font-medium text-[var(--fg-muted)]"
            >
              Customer-facing introduction (optional)
            </label>
            {/* Presentation only. Compliance facts are not editable here —
                changing an answer means going back to the questionnaire,
                because the report must not become a second record. */}
            <Textarea
              id="export-intro"
              rows={2}
              value={introduction}
              onChange={(event) => setIntroduction(event.target.value)}
              placeholder="An optional note to open the report with."
            />
          </div>
        )}

        <dl className="flex flex-wrap gap-x-6 gap-y-1 rounded-md bg-[var(--bg-subtle)] px-4 py-3">
          {[
            ["Customer", preview.customer_name ?? "Not recorded"],
            ["Review", preview.review_title],
            ["Status", preview.review_status_label],
            [
              "Completion",
              `${preview.progress.approved} / ${preview.progress.total} approved · ${preview.progress.percent_complete}%`,
            ],
            ["Version", `${format} v${preview.next_version}`],
          ].map(([label, value]) => (
            <div key={label} className="flex items-baseline gap-1.5">
              <dt className="text-xs text-[var(--fg-subtle)]">{label}</dt>
              <dd className="text-sm text-[var(--fg-default)]">{value}</dd>
            </div>
          ))}
        </dl>

        {preview.column_mapping &&
          Object.keys(preview.column_mapping).length > 0 && (
            <section>
              <h3 className="mb-1 text-sm font-semibold text-[var(--fg-default)]">
                Column mapping
              </h3>
              <p className="mb-2 text-xs text-[var(--fg-subtle)]">
                From {preview.source_filename ?? "the uploaded questionnaire"}.
                Your original upload is not changed.
              </p>
              <ul className="text-sm text-[var(--fg-muted)]">
                {Object.entries(preview.column_mapping).map(([ours, theirs]) => (
                  <li key={ours}>
                    {theirs} → {ours}
                  </li>
                ))}
              </ul>
            </section>
          )}

        <section>
          <h3 className="mb-2 text-sm font-semibold text-[var(--fg-default)]">
            Approved responses ({preview.answers.length})
          </h3>
          <div className="flex flex-col gap-3">
            {preview.answers.map((answer) => (
              <div
                key={answer.question_id}
                className="rounded-md border border-[var(--border-default)] px-4 py-3"
              >
                <p className="text-sm font-medium text-[var(--fg-default)]">
                  {answer.question}
                </p>
                <p className="mt-1 text-sm text-[var(--fg-muted)]">
                  {answer.answer}
                </p>
                {answer.sources.length > 0 && (
                  <p className="mt-1 text-xs text-[var(--fg-subtle)]">
                    Supporting sources: {answer.sources.join(", ")}
                  </p>
                )}
              </div>
            ))}
            {preview.answers.length === 0 && (
              <p className="text-sm text-[var(--fg-muted)]">
                No approved responses to include yet.
              </p>
            )}
          </div>
        </section>

        {preview.disclosures.length > 0 && (
          <section>
            <h3 className="mb-1 text-sm font-semibold text-[var(--fg-default)]">
              Known disclosures and limitations ({preview.disclosures.length})
            </h3>
            {/* §14: an approved answer that records a limitation goes out
                with the limitation. It is shown here so nobody is
                surprised by what the customer will read. */}
            <p className="mb-2 text-xs text-[var(--fg-subtle)]">
              These approved responses record a limitation. They are
              reproduced in full.
            </p>
            <ul className="flex flex-col gap-1 text-sm text-[var(--fg-muted)]">
              {preview.disclosures.map((disclosure) => (
                <li key={disclosure}>— {disclosure}</li>
              ))}
            </ul>
          </section>
        )}

        {preview.documents.length > 0 && (
          <section>
            <h3 className="mb-2 text-sm font-semibold text-[var(--fg-default)]">
              Documents
            </h3>
            <div className="flex flex-col gap-2">
              {preview.documents.map((document) => (
                <div
                  key={document.file_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-[var(--border-default)] px-4 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-[var(--fg-default)]">
                      {document.included ? "✓ " : "○ "}
                      {document.title}
                      {document.version ? ` v${document.version}` : ""}
                    </p>
                    <p className="text-xs text-[var(--fg-subtle)]">
                      {document.kind} · {document.disclosure_label}
                      {document.reason ? ` · ${document.reason}` : ""}
                    </p>
                  </div>
                  {document.eligible ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        onToggleDocument(document.file_id, !document.included)
                      }
                    >
                      {document.included ? "Exclude" : "Include"}
                    </Button>
                  ) : (
                    <span className="text-xs text-[var(--fg-subtle)]">
                      Not available for sharing
                    </span>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        <p className="border-t border-[var(--border-default)] pt-3 text-xs text-[var(--fg-subtle)]">
          {preview.disclaimer}
        </p>
      </div>

      {error && (
        <p role="alert" className="text-sm text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      <DialogFooter className="border-t border-[var(--border-default)] pt-4">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
          Back
        </Button>
        <Button disabled={!preview.ready || generating} onClick={onGenerate}>
          {generating ? "Generating…" : `Generate ${format}`}
        </Button>
      </DialogFooter>
    </>
  );
}
