"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, Download, FileText, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  AuditorIdentity,
  AuditReportPreview,
  AuditReportRecord,
} from "@/lib/types";

/** The last step of a completed audit: read the report, then issue it.
 *
 * The two steps are the feature. Clicking Preview must not produce a
 * PDF — an audit report is a statement somebody puts their name to, and
 * they have to read what it says while it is still only data on a
 * screen. Only the second click makes a document.
 *
 * The preview is a read. Opening it and closing it leaves nothing
 * behind, so Generated reports means "reports issued" rather than
 * "reports somebody considered".
 *
 * Two clocks run through the contents and both are labelled: what the
 * auditor concluded, which cannot move, and where remediation stands,
 * which moves constantly. A report showing only one of them either
 * erases a finding that was raised or pretends nothing was ever fixed.
 */
function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-[var(--border-default)] pt-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        {title}
      </h3>
      {hint && <p className="mt-1 text-xs text-[var(--fg-subtle)]">{hint}</p>}
      <div className="mt-2 text-sm text-[var(--fg-default)]">{children}</div>
    </section>
  );
}

/** The auditor as fields, not as a name with a suffix.
 *
 * "Zach Warren (external)" glued two claims into one string, and the
 * second was inferred from whether an account happened to be linked. An
 * auditor nobody has classified is reported as unresolved rather than
 * assigned a side.
 */
function auditorRows(auditor: AuditorIdentity): [string, string][] {
  const rows: [string, string][] = [
    ["Auditor", auditor.name ?? "Not recorded"],
  ];
  if (auditor.type_label) rows.push(["Auditor type", auditor.type_label]);
  if (auditor.organization) {
    rows.push(["Auditor organization", auditor.organization]);
  } else if (auditor.unresolved) {
    rows.push(["Auditor type", "Not recorded for this audit"]);
  }
  return rows;
}

function Facts({
  rows,
  className,
}: {
  rows: [string, string | null][];
  className?: string;
}) {
  return (
    <dl
      className={`grid grid-cols-[minmax(0,10rem)_1fr] gap-x-4 gap-y-1.5 ${
        className ?? ""
      }`}
    >
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-xs text-[var(--fg-muted)]">{label}</dt>
          <dd className="text-sm text-[var(--fg-default)]">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The counts, with their zeros. "Major 0" is a result; a summary that
 * omits it reads as though nobody looked. */
function Metrics({
  rows,
}: {
  rows: { label: string; value: string; emphasis: boolean }[];
}) {
  return (
    <dl className="mt-2">
      {rows.map((row) => (
        <div
          key={row.label}
          className="flex justify-between border-b border-[var(--border-default)] py-1.5 last:border-0"
        >
          <dt
            className={
              row.emphasis
                ? "text-sm font-semibold text-[var(--fg-default)]"
                : "text-sm text-[var(--fg-muted)]"
            }
          >
            {row.label}
          </dt>
          <dd
            className={
              row.emphasis
                ? "text-sm font-semibold tabular-nums text-[var(--fg-default)]"
                : "text-sm tabular-nums text-[var(--fg-default)]"
            }
          >
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** The same tables the PDF prints, scrolling rather than paginating. */
function Grid({ head, rows }: { head: string[]; rows: (string | null)[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[34rem] border-collapse text-xs">
        <thead>
          <tr className="border-b border-[var(--border-strong)] bg-[var(--bg-subtle)]">
            {head.map((name) => (
              <th
                key={name}
                scope="col"
                className="px-2 py-1.5 text-left align-top font-semibold text-[var(--fg-default)]"
              >
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={index}
              className="border-b border-[var(--border-default)] last:border-0"
            >
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className="px-2 py-1.5 align-top text-[var(--fg-muted)]"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function useAuditReport({
  auditId,
  completed,
}: {
  auditId: string;
  completed: boolean;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<AuditReportPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: reports } = useQuery<AuditReportRecord[]>({
    queryKey: ["compliance", "audits", auditId, "reports"],
    queryFn: () =>
      apiFetch<AuditReportRecord[]>(
        `/api/v1/compliance/audits/${auditId}/reports`,
      ),
  });

  const prepare = useMutation<AuditReportPreview, unknown, void>({
    mutationFn: () =>
      apiFetch<AuditReportPreview>(
        `/api/v1/compliance/audits/${auditId}/report/preview`,
        { method: "POST" },
      ),
    onMutate: () => setError(null),
    onSuccess: (result) => {
      setPreview(result);
      setOpen(true);
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Could not prepare the preview.",
      ),
  });

  const generate = useMutation<AuditReportRecord, unknown, void>({
    mutationFn: () =>
      apiFetch<AuditReportRecord>(
        `/api/v1/compliance/audits/${auditId}/report`,
        { method: "POST", body: { confirm_digest: preview?.digest } },
      ),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setOpen(false);
      setPreview(null);
      await queryClient.invalidateQueries({
        queryKey: ["compliance", "audits", auditId, "reports"],
      });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. No report was generated.",
      ),
  });

  const existing = reports ?? [];
  const stale = existing.some((report) => report.stale);
  // "Updated" only when there is something updated to see. A report
  // already issued and still accurate is previewed under its own name.
  const label = stale ? "Preview updated report" : "Preview audit report";

  return {
    /** The header action. Primary on a completed audit: finishing the
     * review is not the last thing somebody wants to do with it. */
    trigger: completed ? (
      <Button
        size="sm"
        variant={existing.length === 0 || stale ? "default" : "outline"}
        disabled={prepare.isPending}
        onClick={() => prepare.mutate()}
      >
        <FileText className="mr-2 h-4 w-4" aria-hidden="true" />
        {prepare.isPending ? "Preparing…" : label}
      </Button>
    ) : null,

    dialog: (
      <>
        {error && !open && (
          <p role="alert" className="mb-3 text-sm text-[var(--fg-danger)]">
            {error}
          </p>
        )}
        <Dialog
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            // Closing leaves nothing behind. Nothing was created.
            if (!next) {
              setPreview(null);
              setError(null);
            }
          }}
        >
          <DialogContent className="max-h-[86vh] max-w-3xl overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{preview?.title ?? "Audit report"}</DialogTitle>
              <DialogDescription>
                This is the report as it will be issued. Nothing has been
                generated yet.
              </DialogDescription>
            </DialogHeader>

            {preview && (
              <div className="flex flex-col gap-5">
                {preview.blockers.length > 0 && (
                  <div className="rounded-md border border-[var(--warning-300)] bg-[var(--warning-50)] px-3 py-2">
                    {preview.blockers.map((blocker) => (
                      <p
                        key={blocker.code}
                        className="flex gap-2 text-xs text-[var(--warning-800)]"
                      >
                        <TriangleAlert
                          className="mt-0.5 h-3.5 w-3.5 shrink-0"
                          aria-hidden="true"
                        />
                        {blocker.message}
                      </p>
                    ))}
                  </div>
                )}

                {/* The sections below are the PDF's, in the PDF's order and
                    with the PDF's wording. Somebody who approves what they
                    read here must not receive a materially different
                    document. */}
                {!preview.organization_name_configured && (
                  <div className="rounded-md border border-[var(--warning-300)] bg-[var(--warning-50)] px-3 py-2 text-xs text-[var(--warning-800)]">
                    <p className="flex gap-2">
                      <TriangleAlert
                        className="mt-0.5 h-3.5 w-3.5 shrink-0"
                        aria-hidden="true"
                      />
                      <span>
                        This organization has no name configured, so the report
                        cannot name the organization it is about. Set it in{" "}
                        <Link
                          href="/settings/organization"
                          className="underline"
                        >
                          Organization settings
                        </Link>{" "}
                        and preview again.
                      </span>
                    </p>
                  </div>
                )}

                <Section title="1. Audit information">
                  <Facts
                    rows={[
                      ...(preview.organization_name
                        ? ([["Organization", preview.organization_name]] as [
                            string,
                            string,
                          ][])
                        : []),
                      [
                        "Framework",
                        preview.framework_name ?? "Custom scope (no framework)",
                      ],
                      ...(preview.framework_basis
                        ? ([["Requirement set", preview.framework_basis]] as [
                            string,
                            string,
                          ][])
                        : []),
                      ...auditorRows(preview.auditor),
                      ["Audit status", preview.status_label],
                      ["Started", formatDate(preview.started_at)],
                      ["Completed", formatDate(preview.completed_at)],
                      ["Report version", String(preview.next_version)],
                      ["Classification", preview.classification],
                    ]}
                  />
                </Section>

                <Section title="2. Executive summary">
                  {preview.executive_summary.map((sentence) => (
                    <p key={sentence} className="mb-2 leading-relaxed">
                      {sentence}
                    </p>
                  ))}
                  <Metrics rows={preview.metrics} />
                </Section>

                <Section title="3. Scope and methodology">
                  <p className="mb-1 text-xs font-semibold text-[var(--fg-default)]">
                    Scope
                  </p>
                  <p className="mb-3 whitespace-pre-line">
                    {preview.scope || "No scope statement was recorded."}
                  </p>
                  <p className="mb-1 text-xs font-semibold text-[var(--fg-default)]">
                    Methodology
                  </p>
                  {preview.methodology.map((paragraph) => (
                    <p
                      key={paragraph}
                      className="mb-2 text-xs leading-relaxed text-[var(--fg-muted)]"
                    >
                      {paragraph}
                    </p>
                  ))}
                </Section>

                <Section
                  title="4. Audit results summary"
                  hint="Audit conclusions are as recorded by the auditor at completion and do not change. Remediation status is as at the generation date of this report."
                >
                  <p className="mb-1 text-xs font-semibold text-[var(--fg-default)]">
                    Auditor conclusions
                  </p>
                  <Metrics rows={preview.conclusion_summary} />
                  <p className="mb-1 mt-3 text-xs font-semibold text-[var(--fg-default)]">
                    Remediation status
                  </p>
                  <Metrics
                    rows={preview.remediation.map((group) => ({
                      label: group.label,
                      value: String(group.count),
                      emphasis: false,
                    }))}
                  />
                </Section>

                <Section title="5. Findings">
                  {preview.findings_by_severity.length === 0 ? (
                    <p className="text-[var(--fg-muted)]">
                      No audit findings were recorded.
                    </p>
                  ) : (
                    <div className="flex flex-col gap-4">
                      {preview.findings_by_severity.map((group) => (
                        <div key={group.key}>
                          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-default)]">
                            {group.label} ({group.count})
                          </p>
                          <ul className="flex flex-col gap-3">
                            {group.findings.map((finding) => (
                              <li
                                key={finding.id}
                                className="rounded-md border border-[var(--border-default)] px-3 py-2.5"
                              >
                                {/* The requirement is the subject. */}
                                <p className="font-medium">
                                  {[finding.reference_code, finding.requirement_title]
                                    .filter(Boolean)
                                    .join(" — ") || finding.title}
                                </p>
                                <Facts
                                  className="mt-2"
                                  rows={[
                                    ["Auditor conclusion", finding.conclusion_label],
                                    ...(finding.control_title
                                      ? ([["Control", finding.control_title]] as [
                                          string,
                                          string,
                                        ][])
                                      : []),
                                    ...(finding.evidence_state_label
                                      ? ([
                                          [
                                            "Evidence state at audit",
                                            finding.evidence_state_label,
                                          ],
                                        ] as [string, string][])
                                      : []),
                                    [
                                      "Current remediation",
                                      finding.current_status_label,
                                    ],
                                    ...(finding.remediation_owner
                                      ? ([["Owner", finding.remediation_owner]] as [
                                          string,
                                          string,
                                        ][])
                                      : []),
                                    ...(finding.remediation_due
                                      ? ([
                                          ["Due", formatDate(finding.remediation_due)],
                                        ] as [string, string][])
                                      : []),
                                    ...(finding.assessment
                                      ? ([
                                          ["Veyntra assessment", finding.assessment],
                                        ] as [string, string][])
                                      : []),
                                    ...(finding.not_evidenced
                                      ? ([
                                          ["Not evidenced", finding.not_evidenced],
                                        ] as [string, string][])
                                      : []),
                                    ...(finding.auditor_note
                                      ? ([
                                          ["Auditor note", finding.auditor_note],
                                        ] as [string, string][])
                                      : finding.rationale_gap
                                        ? ([
                                            [
                                              "Auditor note",
                                              "No rationale was recorded for this conclusion.",
                                            ],
                                          ] as [string, string][])
                                        : []),
                                  ]}
                                />
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  )}

                  {preview.superseded_findings.length > 0 && (
                    <div className="mt-4">
                      <p className="mb-1 text-xs font-semibold text-[var(--fg-default)]">
                        Replaced conclusions
                      </p>
                      <p className="mb-2 text-xs text-[var(--fg-subtle)]">
                        The auditor revised these conclusions during the audit.
                        They are retained for traceability and are not counted as
                        findings.
                      </p>
                      <ul className="flex flex-col gap-2">
                        {preview.superseded_findings.map((line) => (
                          <li key={line.id}>
                            <p>
                              {line.reference_code ? `${line.reference_code} — ` : ""}
                              {line.conclusion_label}: {line.title}
                            </p>
                            <p className="text-xs text-[var(--fg-subtle)]">
                              {line.superseded_reason}
                            </p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Section>

                <Section
                  title="6. Remediation and verification"
                  hint="Current remediation status as of report generation. Remediation continues after an audit closes; later progress does not change the audit conclusions recorded above."
                >
                  {preview.remediation_rows.length === 0 ? (
                    <p className="text-[var(--fg-muted)]">
                      No remediation items were opened by this audit.
                    </p>
                  ) : (
                    <Grid
                      head={[
                        "Ref",
                        "Finding",
                        "Conclusion",
                        "Owner",
                        "Status",
                        "Due",
                      ]}
                      rows={preview.remediation_rows.map((line) => [
                        line.reference_code ?? "—",
                        line.requirement_title ?? line.title,
                        line.conclusion_label,
                        line.remediation_owner ?? "Unassigned",
                        line.current_status_label,
                        formatDate(line.remediation_due),
                      ])}
                    />
                  )}

                  <p className="mb-1 mt-4 text-xs font-semibold text-[var(--fg-default)]">
                    Verification history
                  </p>
                  {preview.verification.length === 0 ? (
                    <p className="text-[var(--fg-muted)]">
                      No findings had been verified and closed as of the report
                      generation date.
                    </p>
                  ) : (
                    <Grid
                      head={[
                        "Verified",
                        "Ref",
                        "Finding",
                        "Verified by",
                        "What was checked",
                      ]}
                      rows={preview.verification.map((line) => [
                        formatDate(line.verified_at),
                        line.reference_code ?? "—",
                        line.requirement_title ?? line.title,
                        line.verified_by ?? "—",
                        line.verification_note ?? "—",
                      ])}
                    />
                  )}
                </Section>

                <Section
                  title="7. Evidence index"
                  hint="Document versions are as reviewed at the audit preparation date. Documents may have been revised since."
                >
                  {preview.evidence_index.length === 0 ? (
                    <p className="text-[var(--fg-muted)]">
                      No evidence was on file for the requirements in scope.
                    </p>
                  ) : (
                    <Grid
                      head={[
                        "Document",
                        "Version reviewed",
                        "Evidence state at audit",
                        "Reviewed against",
                      ]}
                      rows={preview.evidence_index.map((line) => [
                        line.title,
                        line.version_label,
                        line.evidence_states.join(", ") || "—",
                        line.requirement_codes.join(", "),
                      ])}
                    />
                  )}
                </Section>

                <Section title="8. Known limitations">
                  <ul className="flex list-disc flex-col gap-1 pl-4">
                    {preview.limitations.map((limitation) => (
                      <li key={limitation} className="text-[var(--fg-muted)]">
                        {limitation}
                      </li>
                    ))}
                  </ul>
                </Section>

                <Section title="9. Auditor sign-off">
                  <Facts
                    rows={[
                      ...auditorRows(preview.sign_off.auditor),
                      ["Audit completed", formatDate(preview.sign_off.completed_at)],
                      ["Report generated", formatDate(preview.sign_off.generated_at)],
                      // §7: the person who pressed generate is a different
                      // role from the auditor, and both are named.
                      ...(preview.sign_off.generated_by
                        ? ([
                            ["Generated by", preview.sign_off.generated_by],
                          ] as [string, string][])
                        : []),
                      ["Report version", String(preview.next_version)],
                      ...(preview.sign_off.approved_by
                        ? ([
                            ["Approved by", preview.sign_off.approved_by],
                            [
                              "Approved at",
                              formatDate(preview.sign_off.approved_at),
                            ],
                          ] as [string, string][])
                        : []),
                    ]}
                  />
                  {!preview.sign_off.approved_by && (
                    <p className="mt-2 text-xs text-[var(--fg-subtle)]">
                      No formal sign-off approval is recorded in Veyntra for this
                      audit. The identities and timestamps above are the record.
                    </p>
                  )}
                </Section>

                <Section title="Appendix A — Requirement-by-requirement results">
                  <Grid
                    head={[
                      "Ref",
                      "Requirement",
                      "Evidence state at audit",
                      "Auditor conclusion",
                      "Current remediation status",
                    ]}
                    rows={preview.conclusions.map((line) => [
                      line.reference_code,
                      line.requirement_title,
                      line.evidence_state_label ?? "—",
                      line.decision_label,
                      line.current_remediation_label ?? "—",
                    ])}
                  />
                </Section>

                <p className="border-t border-[var(--border-default)] pt-4 text-xs text-[var(--fg-subtle)]">
                  {preview.disclaimer}
                </p>

                {error && (
                  <p role="alert" className="text-sm text-[var(--fg-danger)]">
                    {error}
                  </p>
                )}
              </div>
            )}

            <DialogFooter>
              <Button
                variant="ghost"
                onClick={() => {
                  setOpen(false);
                  setPreview(null);
                }}
              >
                <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
                Back
              </Button>
              <Button
                disabled={!preview?.ready || generate.isPending}
                onClick={() => generate.mutate()}
              >
                {generate.isPending
                  ? "Generating…"
                  : existing.length === 0
                    ? "Generate PDF"
                    : `Generate new version`}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </>
    ),

    /** The issued reports. Nothing here is ever replaced. */
    history:
      existing.length === 0 ? null : (
        <section id="generated-reports" className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
            Generated reports
          </h2>
          <div className="flex flex-col gap-2">
            {existing.map((report) => (
              <ReportRow key={report.id} auditId={auditId} report={report} />
            ))}
          </div>
        </section>
      ),
  };
}

function ReportRow({
  auditId,
  report,
}: {
  auditId: string;
  report: AuditReportRecord;
}) {
  const [error, setError] = useState<string | null>(null);

  const link = useMutation<{ url: string; filename: string }, unknown, "view" | "download">({
    mutationFn: () =>
      apiFetch<{ url: string; filename: string }>(
        `/api/v1/compliance/audits/${auditId}/reports/${report.id}/download`,
      ),
    onMutate: () => setError(null),
    onSuccess: (result) => window.open(result.url, "_blank", "noopener"),
    onError: () => setError("Could not prepare the file."),
  });

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-6">
        <div className="min-w-0">
          <div className="font-medium text-[var(--fg-default)]">
            Internal Audit Report · Version {report.version}
          </div>
          <div className="text-xs text-[var(--fg-subtle)]">
            {report.file_format.toUpperCase()} · Generated{" "}
            {formatDate(report.generated_at)}
            {report.generated_by_name ? ` by ${report.generated_by_name}` : ""} ·{" "}
            {report.requirements_reviewed} requirement
            {report.requirements_reviewed === 1 ? "" : "s"} reviewed ·{" "}
            {report.findings_count} finding
            {report.findings_count === 1 ? "" : "s"}
          </div>
          {/* The report is unchanged. This only says a newer one can be
              produced — version 1 keeps saying what it said. */}
          {report.stale && (
            <div className="mt-1 text-xs text-[var(--warning-700)]">
              Audit/remediation has changed since this report was generated.
            </div>
          )}
          {error && (
            <p role="alert" className="mt-1 text-xs text-[var(--fg-danger)]">
              {error}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!report.file_id || link.isPending}
            onClick={() => link.mutate("view")}
          >
            View
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!report.file_id || link.isPending}
            onClick={() => link.mutate("download")}
          >
            <Download className="mr-2 h-4 w-4" aria-hidden="true" />
            Download
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
