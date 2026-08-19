"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { ComplianceOverview } from "@/lib/types";

/** Where the organization stands, at the top of the Compliance screen.
 *
 * This is the last two steps of what the product promises — the
 * assessment having run, and readiness plus the missing items showing up
 * — landing where the customer uploaded the document rather than on a
 * framework page they have to go and find. Every figure is a link to the
 * thing it counts, because a number nobody can open is decoration.
 */
export function ReadinessPanel() {
  const { data: overview } = useQuery<ComplianceOverview>({
    queryKey: ["compliance", "overview"],
    queryFn: () => apiFetch<ComplianceOverview>("/api/v1/compliance/overview"),
    // Follows the document pipeline: while something is processing or a
    // reassessment is still catching up, the numbers here are about to
    // change on their own.
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      return data.documents_processing > 0 || data.controls_needing_reassessment > 0
        ? 3000
        : false;
    },
  });

  if (!overview) return null;

  // Nothing adopted means no controls exist, which means an uploaded
  // document has nothing to map to. Saying so is more useful than showing
  // a row of zeros that looks like a failing score.
  if (overview.frameworks.length === 0) {
    return (
      <Card className="mb-8">
        <CardContent className="pt-6">
          <h2 className="mb-1 font-medium text-[var(--fg-default)]">
            Start by adopting a framework
          </h2>
          <p className="mb-3 text-sm leading-relaxed text-[var(--fg-muted)]">
            Adopting GDPR, the EU AI Act or ISO 27001 builds the control set your documents map
            to. Until then Veyntra can read an upload, but has nothing to propose it against.
          </p>
          <Button asChild size="sm">
            <Link href="#frameworks">Choose frameworks</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="mb-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Where you stand
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          {overview.documents_processing > 0 && (
            <span className="flex items-center gap-1.5 text-xs text-[var(--fg-muted)]">
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
              {overview.documents_processing} document
              {overview.documents_processing === 1 ? "" : "s"} processing
            </span>
          )}
          {overview.proposals_awaiting_review > 0 && (
            <Badge variant="outline" className="gap-1">
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              {overview.proposals_awaiting_review} awaiting your review
            </Badge>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {overview.frameworks.map((framework) => (
          <Card key={framework.framework_id}>
            <CardContent className="pt-6">
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <Link
                  href={`/compliance/frameworks/${framework.framework_id}`}
                  className="font-medium text-[var(--fg-default)] hover:underline"
                >
                  {framework.framework_name}
                </Link>
                <span className="text-2xl font-semibold text-[var(--fg-default)]">
                  {framework.readiness.percent}%
                </span>
              </div>

              {/* The number never appears without the arithmetic behind
                  it — the reader's next question is always "which ones". */}
              <p className="text-sm leading-relaxed text-[var(--fg-muted)]">
                {framework.readiness.explanation}
              </p>

              {framework.open_gap_count > 0 && (
                <p className="mt-2 flex items-center gap-1.5 text-sm text-[var(--warning-700)]">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  {framework.open_gap_count} open gap
                  {framework.open_gap_count === 1 ? "" : "s"} — each names the evidence it needs.
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
