"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";

import {
  FrameworkCard,
  ReadinessDisclaimer,
} from "@/components/compliance/framework-card";
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

  // Ordered by what needs a person: frameworks with open actions first,
  // then ones with decisions waiting, then the settled ones. A page that
  // opens on a framework nobody has started buries the one that is
  // failing underneath it.
  const sorted = useMemo(() => {
    return [...(overview?.frameworks ?? [])].sort((a, b) => {
      if (a.open_gap_count !== b.open_gap_count) {
        return b.open_gap_count - a.open_gap_count;
      }
      if (a.readiness.needs_review !== b.readiness.needs_review) {
        return b.readiness.needs_review - a.readiness.needs_review;
      }
      // Then the least ready, which is where the work is.
      if (a.readiness.percent !== b.readiness.percent) {
        return a.readiness.percent - b.readiness.percent;
      }
      return a.framework_name.localeCompare(b.framework_name);
    });
  }, [overview]);

  const summary = useMemo(() => {
    const frameworks = overview?.frameworks ?? [];
    const scored = frameworks.filter((f) => f.readiness.total > 0);
    const average = scored.length
      ? Math.round(
          scored.reduce((total, f) => total + f.readiness.percent, 0) / scored.length
        )
      : 0;
    return [
      { label: "Adopted", value: frameworks.length },
      { label: "Average readiness", value: `${average}%` },
      {
        label: "Open actions",
        value: frameworks.reduce((total, f) => total + f.open_gap_count, 0),
      },
    ];
  }, [overview]);

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
            <Link href="/compliance/frameworks">Choose frameworks</Link>
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

      {/* Three numbers about the whole position, before the per-
          framework detail. A reader who only wants "are we alright"
          stops here. */}
      <dl className="mb-4 grid grid-cols-3 gap-3">
        {summary.map((item) => (
          <div
            key={item.label}
            className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3"
          >
            <dt className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
              {item.label}
            </dt>
            <dd className="mt-1 text-2xl font-semibold text-[var(--fg-default)]">
              {item.value}
            </dd>
          </div>
        ))}
      </dl>

      {/* A list, semantically — it is one. */}
      <ul className="flex flex-col gap-3">
        {sorted.map((framework) => (
          <FrameworkCard key={framework.framework_id} framework={framework} />
        ))}
      </ul>
      <ReadinessDisclaimer />
    </div>
  );
}
