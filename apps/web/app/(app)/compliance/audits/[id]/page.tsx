"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, TriangleAlert } from "lucide-react";

import { useAuditReport } from "@/components/compliance/audit-report";
import { AuditItemRow } from "@/components/compliance/audit-row";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  AuditDetail,
  AuditFinding,
  AuditScope,
  AuditStatus,
  Framework,
} from "@/lib/types";

/** An audit the auditor reviews rather than reconstructs.
 *
 * This page used to open on a blank finding form, with the status
 * dropdown and a completion timestamp that contradicted it. Now it opens
 * on prepared work: how far through the scope the auditor is, what is
 * blocking completion, and the exceptions in the order somebody would
 * work through them.
 *
 * The finding form is still here, at the bottom, as the fallback for
 * something that maps to no requirement. It is no longer the first thing
 * on the page, because it is no longer the normal way to raise one.
 */
type Tab = "review" | "findings" | "scope" | "scope_detail";

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function AuditDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("review");
  const [error, setError] = useState<string | null>(null);

  const { data: audit } = useQuery<AuditDetail>({
    queryKey: ["compliance", "audits", id],
    queryFn: () => apiFetch<AuditDetail>(`/api/v1/compliance/audits/${id}`),
  });

  const move = useMutation({
    mutationFn: (status: AuditStatus) =>
      apiFetch(`/api/v1/compliance/audits/${id}/status`, {
        method: "PATCH",
        body: { status },
      }),
    onMutate: () => setError(null),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "audits"] }),
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was changed.",
      ),
  });

  // Called unconditionally, above the early return: the report query and
  // the preview state are hooks, and an audit that has not loaded yet is
  // not a reason to change their order.
  const report = useAuditReport({
    auditId: id,
    completed: audit?.status === "completed",
  });

  if (!audit) return null;

  const { progress } = audit;
  // A finding the auditor replaced with a later conclusion keeps its
  // severity, its status and its verification, and stops counting as a
  // live finding. Leaving it in the count is what made this page read
  // "18 conclusions, 19 findings" with nothing explaining the extra one.
  const liveFindings = audit.findings.filter((f) => !f.superseded_at);
  const replacedFindings = audit.findings.filter((f) => f.superseded_at);
  const readOnly = audit.status === "completed";
  const exceptions = audit.sections.filter((section) => section.key !== "satisfied");
  const reviewSections = tab === "scope" ? audit.sections : exceptions;

  return (
    <div>
      <PageHeader
        title={audit.title}
        description={
          [
            audit.framework_name,
            audit.auditor_name &&
              `Auditor: ${audit.auditor_name}` +
                // The same vocabulary the report uses. Never "(external)"
                // for a colleague — that label was inferred from a
                // missing account id, not from membership.
                (audit.auditor_type === "external"
                  ? ` · External${
                      audit.auditor_organization
                        ? `, ${audit.auditor_organization}`
                        : ""
                    }`
                  : audit.auditor_type === "internal"
                    ? " · Internal auditor"
                    : ""),
          ]
            .filter(Boolean)
            .join(" · ") || undefined
        }
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={audit.status} label={audit.status_label} />
            {audit.status === "planned" && (
              <Button size="sm" onClick={() => move.mutate("in_progress")}>
                Start audit
              </Button>
            )}
            {audit.status === "in_progress" && (
              <Button
                size="sm"
                disabled={
                  audit.completion_blockers.length > 0 || move.isPending
                }
                onClick={() => move.mutate("completed")}
              >
                Complete audit
              </Button>
            )}
            {/* A completed audit's obvious next action, in the header
                rather than behind a menu. Reviewing 18 requirements and
                then having nowhere to go is where this page stopped. */}
            {report.trigger}
          </div>
        }
      />

      {/* §1: the timestamps follow the status. A planned audit shows
          neither, and never a completion date it does not have. */}
      <Card className="mb-5">
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <p className="text-sm text-[var(--fg-muted)]">
              <span className="text-lg font-semibold text-[var(--fg-default)]">
                {progress.reviewed}
              </span>{" "}
              of {progress.scoped} scoped requirement
              {progress.scoped === 1 ? "" : "s"} reviewed
            </p>
            <p className="text-sm text-[var(--fg-muted)]">
              {progress.percent_reviewed}% reviewed
            </p>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--bg-subtle)]">
            <div
              className="h-full rounded-full bg-[var(--success-600)]"
              style={{ width: `${progress.percent_reviewed}%` }}
            />
          </div>
          {/* §6: "3 open findings" over three observations with fixes
              under way told a compliance manager nothing. What the
              auditor concluded, what the work is doing, and what was
              looked at are three different questions. */}
          <div className="mt-5 grid gap-6 sm:grid-cols-3">
            <div>
              <h3 className="text-[10px] font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
                Auditor conclusions
              </h3>
              <ul className="mt-1 text-sm text-[var(--fg-default)]">
                {(
                  [
                    ["Observations", progress.observations],
                    ["Minor", progress.minor],
                    ["Major", progress.major],
                    ["Critical", progress.critical],
                  ] as const
                ).map(([label, count]) => (
                  <li key={label} className={count ? "" : "text-[var(--fg-subtle)]"}>
                    {count} {label}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-[10px] font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
                Remediation
              </h3>
              <ul className="mt-1 text-sm text-[var(--fg-default)]">
                {(
                  [
                    ["Open", progress.remediation_open],
                    ["In progress", progress.remediation_in_progress],
                    ["Ready for verification", progress.remediation_ready],
                    ["Closed", progress.remediation_closed],
                  ] as const
                ).map(([label, count]) => (
                  <li key={label} className={count ? "" : "text-[var(--fg-subtle)]"}>
                    {count} {label}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-[10px] font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
                Scope
              </h3>
              <ul className="mt-1 text-sm text-[var(--fg-default)]">
                <li>{progress.scoped} in scope</li>
                <li className={progress.not_applicable ? "" : "text-[var(--fg-subtle)]"}>
                  {progress.not_applicable} not applicable
                </li>
                <li className={progress.excluded ? "" : "text-[var(--fg-subtle)]"}>
                  {progress.excluded} excluded by auditor
                </li>
                <li className="text-[var(--fg-subtle)]">
                  {progress.evidence_reviewed} evidence item
                  {progress.evidence_reviewed === 1 ? "" : "s"} reviewed
                </li>
              </ul>
              <button
                type="button"
                onClick={() => setTab("scope_detail")}
                className="mt-1 text-xs font-medium text-[var(--brand-primary)] hover:underline"
              >
                View scope
              </button>
            </div>
          </div>

          <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1">
            {audit.scope && (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-xs text-[var(--fg-subtle)]">Scope</dt>
                <dd className="text-sm text-[var(--fg-default)]">{audit.scope}</dd>
              </div>
            )}
            {audit.started_at && (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-xs text-[var(--fg-subtle)]">Started</dt>
                <dd className="text-sm text-[var(--fg-default)]">
                  {formatDate(audit.started_at)}
                </dd>
              </div>
            )}
            {audit.completed_at && (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-xs text-[var(--fg-subtle)]">Completed</dt>
                <dd className="text-sm text-[var(--fg-default)]">
                  {formatDate(audit.completed_at)}
                </dd>
              </div>
            )}
          </dl>
        </CardContent>
      </Card>

      {/* §17: what is standing in the way, before somebody clicks and is
          refused. The server checks again regardless. */}
      {audit.status !== "completed" && audit.completion_blockers.length > 0 && (
        <div className="mb-5 rounded-lg border border-[var(--warning-300)] bg-[var(--warning-50)] px-5 py-4">
          <div className="flex items-start gap-3">
            <TriangleAlert
              className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-700)]"
              aria-hidden="true"
            />
            <div>
              <p className="text-sm font-medium text-[var(--fg-default)]">
                Not ready to complete
              </p>
              <ul className="mt-1 list-inside list-disc text-sm text-[var(--fg-muted)]">
                {audit.completion_blockers.map((blocker) => (
                  <li key={blocker.code}>{blocker.message}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="mb-4 text-sm text-[var(--fg-danger)]">
          {error}
        </p>
      )}

      <div
        role="tablist"
        aria-label="Audit sections"
        className="mb-4 inline-flex rounded-lg border border-[var(--border-default)] p-1"
      >
        {(
          [
            ["review", `Needs attention (${exceptions.reduce((n, s) => n + s.items.length, 0)})`],
            ["scope", `All scoped requirements (${progress.scoped})`],
            ["findings", `Findings (${liveFindings.length})`],
            ["scope_detail", "Scope"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            id={`audit-tab-${key}`}
            role="tab"
            aria-selected={tab === key}
            aria-controls="audit-panel"
            onClick={() => setTab(key as Tab)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === key
                ? "bg-[var(--bg-subtle)] text-[var(--fg-default)]"
                : "text-[var(--fg-muted)] hover:text-[var(--fg-default)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {report.history}
      {report.dialog}

      <div id="audit-panel" role="tabpanel" aria-labelledby={`audit-tab-${tab}`}>
        {tab === "scope_detail" ? (
          <ScopePanelDetail auditId={id} />
        ) : tab === "findings" ? (
          <FindingsPanel
            audit={audit}
            findings={liveFindings}
            replaced={replacedFindings}
            readOnly={readOnly}
          />
        ) : !audit.framework_id ? (
          <ScopePanel auditId={audit.id} />
        ) : reviewSections.length === 0 ? (
          <EmptyState
            title="Nothing needs your attention"
            description="Every scoped requirement is either satisfied or already decided. The full scope is under All scoped requirements."
          />
        ) : (
          reviewSections.map((section) => (
            <div key={section.key} className="mb-6">
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                {section.label} · {section.items.length}
              </h2>
              {section.items.map((item) => (
                <AuditItemRow
                  key={item.id}
                  auditId={id}
                  item={item}
                  readOnly={readOnly}
                />
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/** Attaching a framework to an audit that was opened without one.
 *
 * These exist: an "ISO 42001 Internal Audit" that is a title and nothing
 * to scope against, because the audit was created before a framework
 * could be chosen. Making somebody abandon the record and open a second
 * audit for the same engagement is a worse answer than letting them
 * attach the framework they meant.
 */
function ScopePanel({ auditId }: { auditId: string }) {
  const queryClient = useQueryClient();
  const [frameworkId, setFrameworkId] = useState("");
  const [scope, setScope] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: frameworks } = useQuery<Framework[]>({
    queryKey: ["compliance", "frameworks"],
    queryFn: () => apiFetch<Framework[]>("/api/v1/compliance/frameworks"),
  });

  const save = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/audits/${auditId}`, {
        method: "PATCH",
        body: {
          framework_id: frameworkId,
          ...(scope.trim() ? { scope: scope.trim() } : {}),
        },
      }),
    onMutate: () => setError(null),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "audits"] }),
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was changed.",
      ),
  });

  return (
    <Card>
      <CardContent className="pt-6">
        <h2 className="text-sm font-semibold text-[var(--fg-default)]">
          This audit has nothing to scope against
        </h2>
        <p className="mt-1 text-sm text-[var(--fg-muted)]">
          Pick the framework it is being run against and Veyntra will
          prepare it from your current compliance state — the applicable
          requirements, the controls answering them, the evidence on file
          and what is missing.
        </p>
        <form
          className="mt-4 flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (frameworkId) save.mutate();
          }}
        >
          <select
            aria-label="Framework"
            value={frameworkId}
            onChange={(event) => setFrameworkId(event.target.value)}
            className="flex h-9 rounded-md border border-[var(--border-strong)] bg-[var(--bg-default)] px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          >
            <option value="">Choose a framework</option>
            {(frameworks ?? []).map((framework) => (
              <option key={framework.id} value={framework.id}>
                {framework.name}
              </option>
            ))}
          </select>
          <Textarea
            aria-label="Scope"
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            rows={2}
            placeholder="Scope — what this audit covers"
          />
          <div>
            <Button type="submit" disabled={!frameworkId || save.isPending}>
              {save.isPending ? "Preparing…" : "Prepare audit"}
            </Button>
          </div>
        </form>
        {error && (
          <p role="alert" className="mt-2 text-sm text-[var(--fg-danger)]">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** Every requirement the framework has, and why it is or is not here.
 *
 * "3 requirements in scope" is not an answer on its own — the first
 * question anybody defending the report gets is what happened to the
 * other fifteen. Not applicable and excluded-by-the-auditor are
 * different answers with different consequences, so they are shown
 * apart and each carries its reason.
 */
function ScopePanelDetail({ auditId }: { auditId: string }) {
  const { data: scope } = useQuery<AuditScope>({
    queryKey: ["compliance", "audits", auditId, "scope"],
    queryFn: () =>
      apiFetch<AuditScope>(`/api/v1/compliance/audits/${auditId}/scope`),
  });

  if (!scope) return null;
  if (scope.lines.length === 0) {
    return (
      <EmptyState
        title="No framework scope"
        description="This audit is not scoped against a framework, so there are no requirements to list."
      />
    );
  }

  const groups = [
    ["included", "In scope", scope.included],
    ["excluded", "Excluded by the auditor", scope.excluded],
    ["not_applicable", "Not applicable to this organization", scope.not_applicable],
  ] as const;

  return (
    <div>
      {groups.map(([key, label, count]) => {
        const lines = scope.lines.filter((line) => line.disposition === key);
        if (lines.length === 0) return null;
        return (
          <div key={key} className="mb-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
              {label} · {count}
            </h2>
            <div className="flex flex-col gap-2">
              {lines.map((line) => (
                <Card key={line.reference_code}>
                  <CardContent className="pt-5">
                    <div className="text-xs font-medium text-[var(--fg-subtle)]">
                      {line.reference_code}
                    </div>
                    <div className="font-medium text-[var(--fg-default)]">
                      {line.title}
                    </div>
                    {line.reason && (
                      <p className="mt-1 text-sm text-[var(--fg-muted)]">
                        {line.reason}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** The findings raised, and what has to happen to each of them. */
function FindingsPanel({
  audit,
  findings,
  replaced,
  readOnly,
}: {
  audit: AuditDetail;
  findings: AuditFinding[];
  replaced: AuditFinding[];
  readOnly: boolean;
}) {
  if (findings.length === 0 && replaced.length === 0) {
    return (
      <EmptyState
        title="No findings raised"
        description="Findings are raised from a decision on a scoped requirement, so they carry the requirement, control and evidence with them."
      />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {findings.map((finding) => (
        <FindingCard
          key={finding.id}
          auditId={audit.id}
          finding={finding}
          readOnly={readOnly}
        />
      ))}

      {/* Kept, labelled, and out of the counts. An auditor who revised a
          conclusion after verifying the first one leaves two rows for one
          requirement; deleting the earlier one would rewrite a
          verification somebody signed. */}
      {replaced.length > 0 && (
        <section className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
            Replaced conclusions ({replaced.length})
          </h3>
          <p className="mt-1 mb-2 text-xs text-[var(--fg-subtle)]">
            The auditor revised these during the audit. They are retained for
            traceability and are not counted as findings.
          </p>
          <div className="flex flex-col gap-2">
            {replaced.map((finding) => (
              <Card key={finding.id}>
                <CardContent className="pt-6">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={finding.severity} />
                    <span className="text-sm text-[var(--fg-default)]">
                      {finding.requirement_code
                        ? `${finding.requirement_code} — `
                        : ""}
                      {finding.title}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[var(--fg-subtle)]">
                    {finding.superseded_reason ??
                      "Replaced by a later conclusion on the same requirement."}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function FindingCard({
  auditId,
  finding,
  readOnly,
}: {
  auditId: string;
  finding: AuditFinding;
  readOnly: boolean;
}) {
  const queryClient = useQueryClient();
  const [verifying, setVerifying] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const act = useMutation({
    mutationFn: ({ action, body }: { action: string; body?: unknown }) =>
      apiFetch(
        `/api/v1/compliance/audits/${auditId}/findings/${finding.id}/${action}`,
        { method: "POST", body },
      ),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setVerifying(false);
      setNote("");
      await queryClient.invalidateQueries({ queryKey: ["compliance", "audits"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was changed.",
      ),
  });

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {finding.requirement_code && (
              <div className="text-xs font-medium text-[var(--fg-subtle)]">
                {finding.requirement_code}
                {finding.control_title ? ` · ${finding.control_title}` : ""}
              </div>
            )}
            <div className="font-medium text-[var(--fg-default)]">
              {finding.title}
            </div>
            {finding.description && (
              <p className="mt-1 text-sm text-[var(--fg-muted)]">
                {finding.description}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <SeverityBadge severity={finding.severity} />
            <StatusBadge status={finding.status} label={finding.status_label} />
          </div>
        </div>

        {finding.evidence_snapshot.length > 0 && (
          <p className="mt-2 text-xs text-[var(--fg-subtle)]">
            Evidence reviewed:{" "}
            {finding.evidence_snapshot.map((entry) => entry.title).join(", ")}
          </p>
        )}

        {finding.verification_note && finding.status === "closed" && (
          <div className="mt-3 flex items-start gap-2 rounded-md bg-[var(--bg-subtle)] px-3 py-2">
            <CheckCircle2
              className="mt-0.5 h-4 w-4 shrink-0 text-[var(--success-600)]"
              aria-hidden="true"
            />
            <div className="text-sm text-[var(--fg-muted)]">
              {finding.verified_at && (
                <span className="font-medium text-[var(--fg-default)]">
                  Closed {formatDate(finding.verified_at)}.{" "}
                </span>
              )}
              {finding.verification_note}
            </div>
          </div>
        )}

        {!readOnly && finding.status !== "closed" && (
          <div className="mt-4">
            {verifying ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (note.trim()) {
                    act.mutate({ action: "verify", body: { note: note.trim() } });
                  }
                }}
              >
                <label
                  htmlFor={`verify-${finding.id}`}
                  className="mb-1.5 block text-xs font-medium text-[var(--fg-muted)]"
                >
                  What you checked, and what it showed
                </label>
                <Textarea
                  id={`verify-${finding.id}`}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  rows={3}
                  autoFocus
                />
                <div className="mt-2 flex gap-2">
                  <Button type="submit" size="sm" disabled={!note.trim() || act.isPending}>
                    Verify and close
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setVerifying(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </form>
            ) : (
              <div className="flex flex-wrap gap-2">
                {finding.status !== "ready_for_verification" && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={act.isPending}
                    onClick={() => act.mutate({ action: "ready" })}
                  >
                    Mark remediation done
                  </Button>
                )}
                <Button size="sm" onClick={() => setVerifying(true)}>
                  Verify and close
                </Button>
                {finding.status === "ready_for_verification" && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={act.isPending}
                    onClick={() =>
                      act.mutate({ action: "reopen", body: { note: null } })
                    }
                  >
                    More work needed
                  </Button>
                )}
              </div>
            )}
          </div>
        )}

        {error && (
          <p role="alert" className="mt-2 text-sm text-[var(--fg-danger)]">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
