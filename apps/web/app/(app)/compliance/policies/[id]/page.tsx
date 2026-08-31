"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileText, Sparkles } from "lucide-react";

import { AssessmentBadge } from "@/components/compliance/assessment-badge";
import {
  PolicyReviewBadge,
  PolicyStatusBadge,
} from "@/components/compliance/policy-status-badge";
import { UploadNewVersion } from "@/components/documents/upload-version";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import { CARD_LINK_FOCUS } from "@/lib/focus";
import type { AuditEvent, Membership, PolicyDetail } from "@/lib/types";

/** One policy: what document it is, who governs it, and its history.
 *
 * The compliance relationships are read from the evidence the document
 * already produced — not a second mapping the customer has to maintain.
 * Version history is append-only: a superseded document stays readable,
 * because "what did your retention policy say in March" is a question an
 * auditor asks.
 */
function formatDate(value: string | null): string {
  return value
    ? new Date(value).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "Not set";
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        {title}
      </h2>
      {children}
    </div>
  );
}

export default function PolicyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [ownerId, setOwnerId] = useState("");
  const [version, setVersion] = useState("");
  const [nextReview, setNextReview] = useState("");
  const [frequency, setFrequency] = useState("");

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["compliance", "policies"] });
    queryClient.invalidateQueries({ queryKey: ["compliance", "policies", id] });
  };

  const {
    data: policy,
    isLoading,
    error,
  } = useQuery<PolicyDetail>({
    queryKey: ["compliance", "policies", id],
    queryFn: () => apiFetch<PolicyDetail>(`/api/v1/compliance/policies/${id}`),
    retry: false,
  });

  const { data: members } = useQuery<Membership[]>({
    queryKey: ["organization", "members"],
    queryFn: () =>
      apiFetch<Membership[]>("/api/v1/organizations/current/members"),
    enabled: editing,
  });

  // The real audit trail, filtered to this policy. Reading it needs the
  // `audit.read` permission, so this is allowed to come back empty for a
  // user who cannot see it — better than a screen that refuses to load.
  const { data: activity } = useQuery<AuditEvent[]>({
    queryKey: ["compliance", "policies", id, "activity"],
    queryFn: () =>
      apiFetch<AuditEvent[]>(`/api/v1/audit-events?object_id=${id}&limit=50`),
    enabled: !!policy,
    retry: false,
  });

  const saveGovernance = useMutation({
    mutationFn: () =>
      apiFetch<PolicyDetail>(`/api/v1/compliance/policies/${id}/governance`, {
        method: "PATCH",
        body: {
          ...(ownerId ? { owner_id: ownerId } : {}),
          ...(version.trim() ? { version: version.trim() } : {}),
          ...(nextReview
            ? { next_review_at: new Date(nextReview).toISOString() }
            : {}),
          ...(frequency ? { review_frequency_months: Number(frequency) } : {}),
        },
      }),
    onSuccess: () => {
      setEditing(false);
      invalidate();
    },
  });

  const approve = useMutation({
    mutationFn: () =>
      apiFetch<PolicyDetail>(`/api/v1/compliance/policies/${id}/approve`, {
        method: "POST",
        body: {},
      }),
    onSuccess: invalidate,
  });

  if (isLoading)
    return <p className="text-sm text-[var(--fg-muted)]">Loading…</p>;

  if (error) {
    const status = error instanceof ApiError ? error.status : null;
    return (
      <p className="text-sm text-[var(--fg-muted)]">
        {status === 404 || status === 403
          ? "Policy not found."
          : "Could not load this policy. Please try again."}
      </p>
    );
  }

  if (!policy) return null;

  const mutationError = saveGovernance.error ?? approve.error;

  return (
    <div>
      <PageHeader
        title={policy.title}
        description={policy.category ?? undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {policy.status !== "approved" && (
              <Button
                size="sm"
                disabled={approve.isPending}
                onClick={() => approve.mutate()}
              >
                <CheckCircle2
                  className="mr-1.5 h-3.5 w-3.5"
                  aria-hidden="true"
                />
                Approve policy
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditing((v) => !v)}
            >
              {editing ? "Cancel" : "Edit governance"}
            </Button>
            {/* One policy across every version of the document behind
                it. Replacing the document here keeps this governance
                record — the owner, the approval history, the review
                date — rather than starting a second policy for the same
                obligation. */}
            {policy.file_id && (
              <UploadNewVersion
                supersedesFileId={policy.file_id}
                documentTitle={policy.title}
              />
            )}
          </div>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <PolicyStatusBadge status={policy.status} />
        <PolicyReviewBadge
          reviewState={policy.review_state}
          daysUntilReview={policy.days_until_review}
        />
        {policy.detected_automatically && (
          <Badge variant="outline" className="gap-1">
            <Sparkles className="h-3 w-3" aria-hidden="true" />
            Found in your documents
          </Badge>
        )}
      </div>

      {mutationError && (
        <p className="mb-4 text-sm text-[var(--critical-600)]">
          {mutationError instanceof ApiError
            ? mutationError.message
            : "Something went wrong."}
        </p>
      )}

      {policy.missing_governance.length > 0 && (
        <Card className="mb-6 border-[var(--warning-500)]/35 bg-[var(--warning-50)]">
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-[var(--warning-700)]">
              Veyntra needs {policy.missing_governance.length} more{" "}
              {policy.missing_governance.length === 1 ? "detail" : "details"}
            </p>
            {/* Named rather than guessed. The product cannot know who owns
                a document or whether the organization approved it, and a
                plausible default would be a compliance record nobody
                wrote. */}
            <p className="mt-1 text-sm leading-relaxed text-[var(--warning-700)]/90">
              {policy.missing_governance.join(", ")} — Veyntra left these blank
              because it cannot determine them from the document.
            </p>
          </CardContent>
        </Card>
      )}

      {editing && (
        <Card className="mb-6">
          <CardContent className="flex flex-col gap-3 pt-6">
            <label className="text-sm text-[var(--fg-muted)]">
              Owner
              <select
                className="mt-1 flex h-9 w-full rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 text-sm text-[var(--fg-default)]"
                value={ownerId}
                onChange={(e) => setOwnerId(e.target.value)}
              >
                <option value="">Select a person…</option>
                {members?.map((member) => (
                  <option key={member.user_id} value={member.user_id}>
                    {member.user_id}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-[var(--fg-muted)]">
              Version
              <Input
                className="mt-1"
                placeholder="e.g. 2.1"
                value={version}
                onChange={(e) => setVersion(e.target.value)}
              />
            </label>
            <label className="text-sm text-[var(--fg-muted)]">
              Next review date
              <Input
                className="mt-1"
                type="date"
                value={nextReview}
                onChange={(e) => setNextReview(e.target.value)}
              />
            </label>
            <label className="text-sm text-[var(--fg-muted)]">
              Review every (months)
              <Input
                className="mt-1"
                type="number"
                min={1}
                max={120}
                placeholder="12"
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
              />
            </label>
            <div>
              <Button
                size="sm"
                disabled={saveGovernance.isPending}
                onClick={() => saveGovernance.mutate()}
              >
                Save governance
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Section title="Current document">
        {policy.file_id ? (
          <Card>
            <CardContent className="pt-6">
              <p className="flex items-center gap-2 font-medium text-[var(--fg-default)]">
                <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
                {/* The same Document Detail route every other surface
                    opens. No link when the document is not indexed. */}
                {policy.document_href ? (
                  <Link
                    href={policy.document_href}
                    className="hover:text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                  >
                    {policy.document_filename ?? "Linked document"}
                  </Link>
                ) : (
                  (policy.document_filename ?? "Linked document")
                )}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Badge variant="success">Analyzed</Badge>
                {policy.document_index_status === "indexed" && (
                  <Badge variant="secondary" className="gap-1">
                    <Sparkles className="h-3 w-3" aria-hidden="true" />
                    Indexed for Copilot
                  </Badge>
                )}
              </div>
              <p className="mt-2 text-sm text-[var(--fg-muted)]">
                {policy.evidence_count} evidence item
                {policy.evidence_count === 1 ? "" : "s"} · mapped to{" "}
                {policy.control_count} control
                {policy.control_count === 1 ? "" : "s"}
              </p>
              <Button asChild size="sm" variant="outline" className="mt-3">
                <Link href="/documents">View document analysis</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <p className="text-sm text-[var(--fg-muted)]">
            No document linked. Upload one under Documents and Veyntra will
            attach it here.
          </p>
        )}
      </Section>

      <Section title="Governance">
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          {[
            ["Owner", policy.owner_id ? "Assigned" : "Not assigned"],
            ["Version", policy.version ?? "Not set"],
            [
              "Approved",
              policy.approved_at
                ? formatDate(policy.approved_at)
                : "Not approved",
            ],
            ["Effective date", formatDate(policy.effective_date)],
            ["Next review", formatDate(policy.next_review_at)],
            [
              "Review cadence",
              policy.review_frequency_months
                ? `Every ${policy.review_frequency_months} months`
                : "Not set",
            ],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex justify-between gap-4 border-b border-[var(--border-default)] py-1.5"
            >
              <dt className="text-sm text-[var(--fg-subtle)]">{label}</dt>
              <dd className="text-sm text-[var(--fg-default)]">{value}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title="Compliance relationships">
        {policy.framework_names.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {policy.framework_names.map((name) => (
              <Badge key={name} variant="outline">
                {name}
              </Badge>
            ))}
          </div>
        )}
        {policy.controls.length === 0 ? (
          <p className="text-sm text-[var(--fg-muted)]">
            No controls are evidenced by this document yet.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {policy.controls.map((control) => (
              <Link
                key={control.id}
                href={`/compliance/controls/${control.id}`}
                className={CARD_LINK_FOCUS}
              >
                <Card className="transition-colors hover:border-[var(--border-strong)]">
                  <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
                    <span className="text-sm text-[var(--fg-default)]">
                      {control.title}
                    </span>
                    <AssessmentBadge
                      status={control.assessment_status}
                      label={control.assessment_label}
                    />
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </Section>

      <Section title="Version history">
        <div className="flex flex-col gap-2">
          {policy.versions.map((entry) => (
            <Card key={entry.id}>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[var(--fg-default)]">
                    {entry.version
                      ? `v${entry.version}`
                      : "Version not recorded"}
                    {entry.status === "current" && " — Current"}
                  </p>
                  <p className="text-xs text-[var(--fg-subtle)]">
                    {entry.filename ?? "Document"}
                    {entry.approved_at &&
                      ` · approved ${formatDate(entry.approved_at)}`}
                    {entry.superseded_at &&
                      ` · superseded ${formatDate(entry.superseded_at)}`}
                  </p>
                </div>
                <Badge
                  variant={entry.status === "current" ? "success" : "outline"}
                >
                  {entry.status === "current" ? "Current" : "Superseded"}
                </Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="Activity">
        {activity && activity.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">
            No activity recorded yet.
          </p>
        )}
        <ol className="flex flex-col gap-2">
          {activity?.map((event, index) => (
            <li
              key={index}
              className="flex flex-wrap items-baseline gap-x-2 text-sm"
            >
              <span className="text-[var(--fg-default)]">
                {event.label ?? event.action}
              </span>
              <span className="text-xs text-[var(--fg-subtle)]">
                {new Date(event.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}
