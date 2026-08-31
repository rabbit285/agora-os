"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileText, Sparkles } from "lucide-react";

import {
  PolicyReviewBadge,
  PolicyStatusBadge,
} from "@/components/compliance/policy-status-badge";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { CARD_LINK_FOCUS } from "@/lib/focus";
import type { Policy } from "@/lib/types";

/** "Which policies do we have, who owns them, and are they current?"
 *
 * Every record here is created from a document the customer already
 * uploaded. The old flow asked them to upload `03_AI_Governance_Policy.docx`,
 * watch Veyntra read it and map it to ten controls, then go to another
 * screen, press "Add policy" and type the title again. The product knew
 * the title. Asking twice is data entry the system could have done.
 *
 * There is no "Add policy" button. A governance record without a
 * document is a title in a list — it governs nothing, evidences nothing,
 * and the first thing anyone would do with it is attach the document
 * that would have created it anyway. Upload the document; the record
 * follows.
 */
const FILTERS = [
  { key: "all", label: "All" },
  { key: "needs_review", label: "Needs review" },
  { key: "approved", label: "Approved" },
  { key: "review_due", label: "Review due" },
  { key: "retired", label: "Retired" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

function matches(policy: Policy, filter: FilterKey): boolean {
  if (filter === "all") return true;
  if (filter === "review_due") {
    return policy.review_state === "overdue" || policy.review_state === "due_soon";
  }
  if (filter === "needs_review") {
    return policy.status === "needs_review" || policy.status === "draft";
  }
  return policy.status === filter;
}

function formatDate(value: string | null): string {
  return value
    ? new Date(value).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "Not set";
}

export default function PoliciesPage() {
  const [filter, setFilter] = useState<FilterKey>("all");

  const { data: policies, isLoading } = useQuery<Policy[]>({
    queryKey: ["compliance", "policies"],
    queryFn: () => apiFetch<Policy[]>("/api/v1/compliance/policies"),
    // Detection runs in the background the first time this list is
    // opened, so a tenant with existing documents sees its records
    // appear rather than an empty page it has to reload.
    refetchInterval: (query) => ((query.state.data ?? []).length === 0 ? 3000 : false),
  });


  const metrics = useMemo(() => {
    const all = policies ?? [];
    return [
      { label: "Policies", value: all.length },
      {
        label: "Needs review",
        value: all.filter((p) => p.status === "needs_review" || p.status === "draft").length,
      },
      {
        label: "Review due",
        value: all.filter(
          (p) => p.review_state === "overdue" || p.review_state === "due_soon"
        ).length,
      },
      { label: "Approved", value: all.filter((p) => p.status === "approved").length },
    ];
  }, [policies]);

  const visible = (policies ?? []).filter((policy) => matches(policy, filter));
  const incomplete = (policies ?? []).filter((p) => p.missing_governance.length > 0);

  return (
    <div>
      <PageHeader
        title="Policies"
        description="The policies Veyntra identified from your documents — who owns them, whether they are approved, and when they are next due for review."

      />

      {policies && policies.length > 0 && (
        <>
          <dl className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {metrics.map((metric) => (
              <div
                key={metric.label}
                className="rounded-[var(--radius-md)] border border-[var(--border-default)] p-3"
              >
                <dt className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                  {metric.label}
                </dt>
                <dd className="mt-1 text-2xl font-semibold text-[var(--fg-default)]">
                  {metric.value}
                </dd>
              </div>
            ))}
          </dl>

          <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter policies">
            {FILTERS.map((option) => (
              <Button
                key={option.key}
                size="sm"
                variant={filter === option.key ? "default" : "outline"}
                aria-pressed={filter === option.key}
                onClick={() => setFilter(option.key)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </>
      )}

      {/* Never "no managed policies yet" while policy documents exist —
          that was the confusion this page was built to remove. */}
      {policies && policies.length === 0 && !isLoading && (
        <EmptyState
          icon={FileText}
          title="No policies yet"
          description="Upload a policy document and Veyntra will identify it, extract compliance evidence and create its governance record automatically."
        />
      )}

      {incomplete.length > 0 && filter === "all" && (
        <Card className="mb-4 border-[var(--warning-500)]/35 bg-[var(--warning-50)]">
          <CardContent className="pt-6">
            <p className="flex items-center gap-2 text-sm font-medium text-[var(--warning-700)]">
              <Sparkles className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {incomplete.length}{" "}
              {incomplete.length === 1 ? "policy needs" : "policies need"} governance setup
            </p>
            <p className="mt-1 text-sm leading-relaxed text-[var(--warning-700)]/90">
              Veyntra found these in your documents. It cannot know who owns them or
              whether your organization approved them, so it left those blank rather than
              guessing.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {incomplete.slice(0, 5).map((policy) => (
                <Button key={policy.id} asChild size="sm" variant="outline">
                  <Link href={`/compliance/policies/${policy.id}`}>{policy.title}</Link>
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-2">
        {visible.map((policy) => (
          <Link
            key={policy.id}
            href={`/compliance/policies/${policy.id}`}
            className={CARD_LINK_FOCUS}
          >
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex flex-wrap items-start justify-between gap-4 pt-6">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-[var(--fg-default)]">
                      {policy.title}
                    </span>
                    <PolicyStatusBadge status={policy.status} />
                    <PolicyReviewBadge
                      reviewState={policy.review_state}
                      daysUntilReview={policy.days_until_review}
                    />
                  </div>

                  <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-[var(--fg-muted)]">
                    <div className="flex gap-1">
                      <dt className="text-[var(--fg-subtle)]">Owner:</dt>
                      <dd>{policy.owner_id ? "Assigned" : "Not assigned"}</dd>
                    </div>
                    <div className="flex gap-1">
                      <dt className="text-[var(--fg-subtle)]">Version:</dt>
                      <dd>{policy.version ?? "Not set"}</dd>
                    </div>
                    <div className="flex gap-1">
                      <dt className="text-[var(--fg-subtle)]">Next review:</dt>
                      <dd>{formatDate(policy.next_review_at)}</dd>
                    </div>
                  </dl>

                  <p className="mt-1 text-xs text-[var(--fg-subtle)]">
                    {policy.control_count} control
                    {policy.control_count === 1 ? "" : "s"}
                    {policy.framework_names.length > 0 && (
                      <> · {policy.framework_names.join(" · ")}</>
                    )}
                    {policy.document_filename && <> · {policy.document_filename}</>}
                  </p>
                </div>

                <div className="flex shrink-0 items-center gap-2 text-sm text-[var(--fg-muted)]">
                  {policy.missing_governance.length > 0 ? "Complete setup" : "View policy"}
                  <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {policies && policies.length > 0 && visible.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">
          No policies match this filter.
        </p>
      )}
    </div>
  );
}
