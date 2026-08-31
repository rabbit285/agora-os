"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CircleAlert, Clock, TriangleAlert } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { PrivacyAttention, PrivacyOverview } from "@/lib/types";

/** What the privacy team has to deal with today.
 *
 * Deliberately not a vanity dashboard. Every number is a link to the
 * records behind it, and every item in Needs attention is a deficiency
 * somebody can act on with the route to the exact record. A figure that
 * leads nowhere is a decoration, and a privacy officer with fifty
 * activities cannot use a decoration.
 *
 * Nothing here concludes anything legal. "Missing lawful basis" is a
 * fact about a form field; "transfer mechanism needs review" says a
 * person should look, not that a transfer is unlawful.
 */
const SEVERITY = {
  overdue: {
    icon: CircleAlert,
    className: "text-[var(--fg-danger)]",
    label: "Overdue",
  },
  urgent: {
    icon: Clock,
    className: "text-[var(--warning-700)]",
    label: "Due soon",
  },
  attention: {
    icon: TriangleAlert,
    className: "text-[var(--warning-700)]",
    label: "Needs attention",
  },
  info: {
    icon: TriangleAlert,
    className: "text-[var(--fg-muted)]",
    label: "Worth a look",
  },
} as const;

function AttentionRow({ item }: { item: PrivacyAttention }) {
  const tone = SEVERITY[item.severity as keyof typeof SEVERITY] ?? SEVERITY.info;
  const Icon = tone.icon;
  return (
    <Link
      href={item.href}
      className="flex gap-3 rounded-md border border-[var(--border-default)] px-3 py-2.5 transition-colors hover:bg-[var(--bg-subtle)]"
    >
      <Icon
        className={`mt-0.5 h-4 w-4 shrink-0 ${tone.className}`}
        aria-hidden="true"
      />
      <div className="min-w-0">
        <p className="text-sm font-medium text-[var(--fg-default)]">
          {item.title}
        </p>
        <p className="mt-0.5 text-xs text-[var(--fg-muted)]">{item.detail}</p>
      </div>
    </Link>
  );
}

export default function PrivacyOverviewPage() {
  const { data: overview, isLoading } = useQuery<PrivacyOverview>({
    queryKey: ["compliance", "privacy", "overview"],
    queryFn: () =>
      apiFetch<PrivacyOverview>("/api/v1/compliance/privacy/overview"),
  });

  if (isLoading || !overview) return null;

  return (
    <div className="flex flex-col gap-6">
      <section>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
          {overview.metrics.map((metric) => (
            <Link
              key={metric.key}
              href={metric.href}
              className="rounded-lg border border-[var(--border-default)] px-3 py-3 transition-colors hover:bg-[var(--bg-subtle)]"
            >
              <div
                className={`text-2xl font-semibold ${
                  metric.tone === "attention"
                    ? "text-[var(--warning-700)]"
                    : "text-[var(--fg-default)]"
                }`}
              >
                {metric.value}
              </div>
              <div className="mt-0.5 text-xs text-[var(--fg-muted)]">
                {metric.label}
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Needs attention
        </h2>
        {overview.attention.length === 0 ? (
          <EmptyState
            title="Nothing needs your attention"
            description="No data request is near its deadline, and every privacy record has what it needs recorded. New work appears here as it arrives."
          />
        ) : (
          <div className="flex flex-col gap-2">
            {overview.attention.map((item) => (
              <AttentionRow key={item.key} item={item} />
            ))}
          </div>
        )}
      </section>

      <Card>
        <CardContent className="pt-6">
          <h3 className="text-sm font-semibold text-[var(--fg-default)]">
            What Veyntra decides, and what you decide
          </h3>
          <p className="mt-1.5 text-xs leading-relaxed text-[var(--fg-muted)]">
            Veyntra calculates deadlines, flags records with information
            missing, and tells you when something is due for review. It does
            not choose a lawful basis, decide whether a DPIA is required, or
            conclude that a transfer is covered — those are judgements this
            product surfaces for a person to make and record.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
