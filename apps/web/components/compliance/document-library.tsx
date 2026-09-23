"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronRight, FileText, GitBranch, Loader2, RefreshCw, ShieldCheck, Sparkles, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { uploadFile } from "@/lib/upload";
import type { ComplianceDocument } from "@/lib/types";

/** Upload a document and watch Veyntra read it.
 *
 * The whole point of this screen is that uploading is the only action.
 * Parsing, classification and control matching happen without being
 * asked for, and the pipeline is shown stage by stage because a product
 * that claims to be doing work owes the user visible evidence that it
 * is. A spinner with no stages is indistinguishable from a hang.
 */

const STAGES: { key: string; label: string }[] = [
  { key: "uploaded", label: "Uploaded" },
  { key: "parsing", label: "Reading" },
  { key: "analyzing", label: "Matching controls" },
  // "Ready" only ever meant "processing finished", which a customer
  // reasonably reads as "this document is fine". Veyntra read it; what
  // it found is the next line down.
  { key: "ready", label: "Analyzed" },
];

// `not_analyzed` is deliberately absent: it is a resting state, not a
// stage. Including it would make every unrelated attachment in the
// organization render as mid-pipeline and poll forever.
const IN_FLIGHT = new Set(["uploaded", "parsing", "analyzing"]);

function ProcessingTrail({ status }: { status: string }) {
  const currentIndex = STAGES.findIndex((s) => s.key === status);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {STAGES.map((stage, index) => {
        const done = currentIndex > index || status === "ready";
        const active = currentIndex === index && status !== "ready";
        return (
          <span key={stage.key} className="flex items-center gap-1.5">
            <span
              className={
                done
                  ? "text-xs text-[var(--success-700)]"
                  : active
                    ? "flex items-center gap-1 text-xs font-medium text-[var(--fg-default)]"
                    : "text-xs text-[var(--fg-subtle)]"
              }
            >
              {active && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
              {stage.label}
            </span>
            {index < STAGES.length - 1 && (
              <span className="text-xs text-[var(--fg-subtle)]" aria-hidden="true">
                →
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}

/** What to say about a document's control mappings.
 *
 * "No control matches proposed" is true of a brand-new organization and
 * badly misleading: it reads as "we looked and your policy evidences
 * nothing", when what happened is that there was nothing to look
 * against. The first thing a customer does in the product should not
 * report a negative finding about work they have not started.
 *
 * The server decides which of the three situations this is — see
 * `_mapping_state` — because it is the only place that knows whether the
 * organization has any controls at all.
 */
function mappingSummary(doc: ComplianceDocument): string {
  if (doc.proposed_count > 0) {
    return `${doc.proposed_count} proposal${doc.proposed_count === 1 ? "" : "s"} awaiting review`;
  }
  if (doc.approved_count > 0) {
    return `${doc.approved_count} approved as evidence`;
  }
  if (doc.mapping_state === "no_controls") {
    return "evidence mapping starts when you adopt a framework";
  }
  return "no control matches proposed";
}

/** Whether Veyntra produced this file, rather than being given it.
 *
 * The distinction is stored on the record rather than guessed from a
 * filename — a customer can upload something called "Audit Report v2",
 * and a library that reclassified it would quietly drop a real document
 * out of the evidence workflow.
 */
function isGenerated(doc: ComplianceDocument): boolean {
  return doc.artifact_type === "generated_output";
}

export function DocumentLibrary() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  // Which half of the library is on screen. Documents Veyntra was given
  // and documents Veyntra produced are different kinds of thing, and
  // listing them together is what made a report look like evidence.
  const [tab, setTab] = useState<"source" | "generated_output">("source");

  const { data: documents } = useQuery<ComplianceDocument[]>({
    queryKey: ["compliance", "documents"],
    queryFn: () => apiFetch<ComplianceDocument[]>("/api/v1/compliance/documents"),
    // Poll only while something is actually moving. A fixed interval
    // would keep hitting the API forever on an idle library.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((d) => IN_FLIGHT.has(d.processing_status)) ? 2000 : false,
  });

  const sourceDocs = (documents ?? []).filter((doc) => !isGenerated(doc));
  const generatedDocs = (documents ?? []).filter(isGenerated);
  const visible = tab === "source" ? sourceDocs : generatedDocs;

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["compliance", "documents"] });
    void queryClient.invalidateQueries({ queryKey: ["compliance", "evidence-suggestions"] });
    // The readiness panel is the visible end of this chain, so it has
    // to move when evidence does.
    void queryClient.invalidateQueries({ queryKey: ["compliance", "overview"] });
  };

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const fileId = await uploadFile(file, { classification: "confidential" });
      // Processing starts here, not on a second click by the user. This
      // one call is what makes "upload once" true.
      return apiFetch("/api/v1/compliance/documents/process", {
        method: "POST",
        body: { file_id: fileId },
      });
    },
    onSuccess: () => {
      setUploadError(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      refresh();
    },
    onError: (error) =>
      setUploadError(error instanceof ApiError ? error.message : (error as Error).message),
  });

  const reprocess = useMutation({
    mutationFn: (fileId: string) =>
      apiFetch("/api/v1/compliance/documents/process", {
        method: "POST",
        body: { file_id: fileId },
      }),
    onSuccess: refresh,
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Document intelligence
      </h2>

      <Card className="mb-4">
        <CardContent className="pt-6">
          <p className="mb-3 text-sm leading-relaxed text-[var(--fg-muted)]">
            Upload a policy, notice or procedure. Veyntra reads it, works out what it is, and
            proposes which of your controls it evidences — you do not need to map anything by
            hand. Proposals appear below for your review; nothing reaches your compliance
            status until you approve it.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            className="text-sm text-[var(--fg-muted)] file:mr-3 file:rounded-[var(--radius-md)] file:border file:border-[var(--border-default)] file:bg-[var(--bg-surface)] file:px-3 file:py-1.5 file:text-sm file:text-[var(--fg-default)]"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
            }}
          />
          {upload.isPending && (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-[var(--fg-muted)]">
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
              Uploading…
            </p>
          )}
          {uploadError && (
            <p className="mt-2 text-sm text-[var(--critical-600)]">{uploadError}</p>
          )}
        </CardContent>
      </Card>

      {documents?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No documents uploaded yet.</p>
      )}

      {(documents?.length ?? 0) > 0 && (
        <div
          role="tablist"
          aria-label="Document library"
          className="mb-4 flex flex-wrap gap-1 border-b border-[var(--border-default)]"
        >
          {(
            [
              [
                "source",
                "Source documents",
                sourceDocs.length,
                "Documents used to support your compliance records.",
              ],
              [
                "generated_output",
                "Generated outputs",
                generatedDocs.length,
                "Reports and exports Veyntra produced from your compliance records.",
              ],
            ] as const
          ).map(([key, label, count, hint]) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              title={hint}
              onClick={() => setTab(key)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                tab === key
                  ? "border-[var(--accent-600)] text-[var(--fg-default)]"
                  : "border-transparent text-[var(--fg-muted)] hover:text-[var(--fg-default)]"
              }`}
            >
              {label}
              <span className="ml-2 text-xs text-[var(--fg-subtle)]">{count}</span>
            </button>
          ))}
        </div>
      )}

      {(documents?.length ?? 0) > 0 && (
        <p className="mb-3 text-xs text-[var(--fg-subtle)]">
          {tab === "source"
            ? "Documents used to support your compliance records."
            : "Reports and exports Veyntra produced from your compliance records. These are results of your compliance work, not evidence for it."}
        </p>
      )}

      {visible.length === 0 && (documents?.length ?? 0) > 0 && (
        <p className="text-sm text-[var(--fg-muted)]">
          {tab === "generated_output"
            ? "Nothing generated yet. Audit reports and security review exports appear here once you produce them."
            : "No source documents yet."}
        </p>
      )}

      <div className="flex flex-col gap-2">
        {visible.map((doc) => (
          // The whole row opens the document — via one real link that
          // stretches over the card, not a click handler on a div. The
          // link keeps its keyboard semantics and its accessible name;
          // everything interactive inside the row sits above it on
          // `relative z-10` so a policy link or a retry button does its
          // own job instead of navigating away.
          <Card
            key={doc.id}
            className={
              doc.href
                ? "relative transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--bg-surface-hover)] focus-within:ring-2 focus-within:ring-[var(--border-focus)]"
                : undefined
            }
          >
            <CardContent className="py-4">
              <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2">
                  <FileText
                    className="h-4 w-4 shrink-0 text-[var(--fg-subtle)]"
                    aria-hidden="true"
                  />
                  <span className="min-w-0">
                    {doc.href ? (
                      <Link
                        href={doc.href}
                        className="font-medium text-[var(--fg-default)] after:absolute after:inset-0 hover:underline focus-visible:outline-none"
                      >
                        {doc.title || doc.original_filename}
                      </Link>
                    ) : (
                      <span className="font-medium text-[var(--fg-default)]">
                        {doc.title || doc.original_filename}
                      </span>
                    )}
                    {/* The filename, once, underneath the name. It is how
                        the customer finds the file on their own disk. */}
                    <span className="block truncate text-xs text-[var(--fg-subtle)]">
                      {doc.original_filename}
                    </span>
                  </span>
                </span>
                <div className="relative z-10 flex shrink-0 flex-wrap items-center gap-1.5">
                  {/* A quiet chevron, so the row reads as openable
                      without a View button on all twenty of them. */}
                  {doc.href && (
                    <ChevronRight
                      className="order-last h-4 w-4 text-[var(--fg-subtle)]"
                      aria-hidden="true"
                    />
                  )}
                  {/* One row is one logical document. When it has more
                      than one version, the row says so and the count is
                      the way into the history — the older versions are
                      not listed here, because they are not other
                      documents. */}
                  {doc.version_count > 1 && (
                    <Badge variant="outline" className="gap-1">
                      <GitBranch className="h-3 w-3" aria-hidden="true" />
                      {doc.version_label ? `${doc.version_label} · ` : ""}
                      {doc.version_count} versions
                    </Badge>
                  )}
                  {/* An undecided version question is why the library
                      briefly holds two rows for one document. Saying so
                      on both rows beats letting it look like the
                      duplicate bug it is not. */}
                  {doc.has_pending_version && (
                    <Badge variant="secondary" className="gap-1">
                      <GitBranch className="h-3 w-3" aria-hidden="true" />
                      Version to confirm
                    </Badge>
                  )}
                  {doc.document_domain && <Badge variant="outline">{doc.document_domain}</Badge>}
                  {/* A result of Veyntra's compliance work, not a source
                      for it. Said on the row because the two used to sit
                      side by side looking identical. */}
                  {isGenerated(doc) && (
                    <Badge variant="secondary" className="gap-1">
                      <Sparkles className="h-3 w-3" aria-hidden="true" />
                      Generated output
                    </Badge>
                  )}
                  {doc.processing_status === "ready" && (
                    <Badge variant="success" className="gap-1">
                      <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                      Analyzed
                    </Badge>
                  )}
                  {/* Whether the Copilot can actually retrieve from this
                      document — a different pipeline from the analysis
                      above, and one that can fail on its own. Showing
                      only "Analyzed" is what let someone ask the Copilot
                      about a document it had never been given. */}
                  {doc.processing_status === "ready" &&
                    doc.index_status === "indexed" && (
                      <Badge variant="secondary" className="gap-1">
                        <Sparkles className="h-3 w-3" aria-hidden="true" />
                        Indexed for Copilot
                      </Badge>
                    )}
                  {doc.processing_status === "ready" &&
                    doc.index_status === "pending" && (
                      <Badge variant="outline" className="gap-1">
                        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                        Indexing for Copilot
                      </Badge>
                    )}
                  {doc.processing_status === "ready" &&
                    (doc.index_status === "failed" ||
                      doc.index_status === "unsupported") && (
                      <Badge variant="destructive" className="gap-1">
                        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                        Not available to Copilot
                      </Badge>
                    )}
                  {(doc.processing_status === "failed" ||
                    doc.processing_status === "unsupported") && (
                    <Badge variant="destructive" className="gap-1">
                      <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                      {doc.processing_status === "unsupported" ? "Cannot read" : "Failed"}
                    </Badge>
                  )}
                </div>
              </div>

              {IN_FLIGHT.has(doc.processing_status) && (
                <ProcessingTrail status={doc.processing_status} />
              )}

              {/* Files that arrived from elsewhere in Veyntra were never
                  submitted for compliance analysis. Offering the action
                  is honest; showing a stalled progress trail is not. */}
              {isGenerated(doc) && (
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-sm text-[var(--fg-muted)]">
                    {doc.origin_label
                      ? `Generated from ${doc.origin_label}.`
                      : "Produced by Veyntra from your compliance records."}
                  </span>
                  {doc.origin_href && (
                    <Link
                      href={doc.origin_href}
                      // Above the row-wide link that opens the document,
                      // so this one does its own job instead of being
                      // swallowed by it.
                      className="relative z-10 text-sm text-[var(--fg-link)] underline"
                    >
                      Open {doc.origin_type === "audit_report" ? "audit" : "review"}
                    </Link>
                  )}
                </div>
              )}
              {!isGenerated(doc) && doc.processing_status === "not_analyzed" && (
                <div className="relative z-10 flex flex-wrap items-center gap-2">
                  <span className="text-sm text-[var(--fg-muted)]">Not analyzed yet.</span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={reprocess.isPending}
                    onClick={() => reprocess.mutate(doc.id)}
                  >
                    <Upload className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                    Analyze for evidence
                  </Button>
                </div>
              )}

              {/* A policy document says so, and links to the record
                  Veyntra created for it. The customer never has to make
                  this connection by hand. */}
              {doc.policy_id && (
                // Above the stretched row link, so this opens the policy
                // record rather than the document behind it.
                <Link
                  href={`/compliance/policies/${doc.policy_id}`}
                  className="relative z-10 mt-1 inline-flex flex-wrap items-center gap-1.5 self-start text-sm text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                >
                  <ShieldCheck className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  Policy detected · {doc.policy_title}
                  {doc.policy_status !== "approved" && " — needs governance review"}
                </Link>
              )}

              {doc.processing_status === "ready" && doc.index_error && (
                <p className="text-sm text-[var(--warning-700)]">{doc.index_error}</p>
              )}

              {doc.processing_status === "ready" && (
                <div className="text-sm text-[var(--fg-muted)]">
                  {doc.document_type && (
                    <span className="text-[var(--fg-default)]">{doc.document_type}</span>
                  )}
                  {/* Shown so "Analyzed" is backed by a number: a
                      document that parsed to nothing can never look like
                      one that simply matched no controls. */}
                  {doc.extracted_characters !== null && (
                    <span> · {doc.extracted_characters.toLocaleString()} characters read</span>
                  )}
                  <span>
                    {" · "}
                    {mappingSummary(doc)}
                  </span>
                  {doc.unverifiable_count > 0 && (
                    <span className="text-[var(--warning-700)]">
                      {" · "}
                      {doc.unverifiable_count} discarded as unverifiable
                    </span>
                  )}
                </div>
              )}

              {(doc.processing_status === "failed" ||
                doc.processing_status === "unsupported") && (
                <div>
                  <p className="text-sm text-[var(--warning-700)]">{doc.processing_error}</p>
                  {/* Only `failed` is retryable — an unsupported content
                      type will fail identically every time, so offering a
                      retry there would just waste the user's time. */}
                  {doc.processing_status === "failed" && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="relative z-10 mt-2"
                      disabled={reprocess.isPending}
                      onClick={() => reprocess.mutate(doc.id)}
                    >
                      <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                      Try again
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
