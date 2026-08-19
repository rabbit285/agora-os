"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Sparkles } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { ReviewCenter } from "@/lib/types";

/** One queue for everything waiting on a person.
 *
 * The whole argument of the product is that AI does the repetitive work
 * and people handle exceptions. That only holds if the exceptions are in
 * one place — spread across six screens, "5 things need you" becomes "go
 * and look everywhere", which is the job the customer was trying to stop
 * doing.
 *
 * An empty queue is a good outcome and says so plainly, rather than
 * padding itself with things that might matter later.
 */

const PRIORITY_VARIANT: Record<string, "destructive" | "outline" | "secondary"> = {
  high: "destructive",
  medium: "outline",
  low: "secondary",
};

export default function ReviewCenterPage() {
  const { data } = useQuery<ReviewCenter>({
    queryKey: ["compliance", "review-center"],
    queryFn: () => apiFetch<ReviewCenter>("/api/v1/compliance/review-center"),
  });

  const active = (data?.categories ?? []).filter((category) => category.count > 0);

  return (
    <div>
      <PageHeader
        title="Review Center"
        description="Every decision waiting on you, in one place."
      />

      {data && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            {/* The ratio the customer is actually buying: work the AI did
                without asking, next to what it could not decide alone. */}
            <p className="text-sm leading-relaxed text-[var(--fg-default)]">
              <span className="inline-flex items-center gap-1.5 font-medium">
                <Sparkles className="h-3.5 w-3.5 text-[var(--brand-primary)]" aria-hidden="true" />
                In the last 7 days
              </span>{" "}
              Veyntra proposed {data.proposals_recently} evidence mapping
              {data.proposals_recently === 1 ? "" : "s"}, accepted{" "}
              {data.auto_accepted_recently} automatically, and left{" "}
              {data.total_needing_review} decision
              {data.total_needing_review === 1 ? "" : "s"} for you.
            </p>
            <p className="mt-2 text-xs leading-relaxed text-[var(--fg-subtle)]">
              A mapping is accepted automatically only when its quoted passage was found in
              your document and the requirement is not one flagged sensitive. Anything
              touching breach notification, DPIAs, prohibited AI practices or human oversight
              always comes to you.
            </p>
          </CardContent>
        </Card>
      )}

      {data && data.total_needing_review === 0 && (
        <Card>
          <CardContent className="flex items-start gap-2.5 pt-6">
            <CheckCircle2
              className="mt-0.5 h-4 w-4 shrink-0 text-[var(--success-600)]"
              aria-hidden="true"
            />
            <div>
              <p className="font-medium text-[var(--fg-default)]">Nothing needs you right now.</p>
              <p className="mt-1 text-sm text-[var(--fg-muted)]">
                Upload a document or adopt a framework and anything Veyntra cannot decide on
                its own will appear here.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-6">
        {active.map((category) => (
          <section key={category.key}>
            <div className="mb-2 flex flex-wrap items-baseline gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                {category.label}
              </h2>
              <Badge variant="secondary">{category.count}</Badge>
            </div>
            <p className="mb-3 text-sm leading-relaxed text-[var(--fg-muted)]">
              {category.description}
            </p>

            <div className="flex flex-col gap-2">
              {category.items.map((item) => (
                <Link key={item.id} href={item.href}>
                  <Card className="transition-colors hover:border-[var(--border-strong)]">
                    <CardContent className="flex items-start justify-between gap-4 py-4">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-[var(--fg-default)]">
                            {item.title}
                          </span>
                          <Badge variant={PRIORITY_VARIANT[item.priority] ?? "secondary"}>
                            {item.priority}
                          </Badge>
                        </div>
                        <p className="mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">
                          {item.detail}
                        </p>
                      </div>
                      <ArrowRight
                        className="mt-1 h-4 w-4 shrink-0 text-[var(--fg-subtle)]"
                        aria-hidden="true"
                      />
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
