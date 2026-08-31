"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Sparkles } from "lucide-react";

import { EvidenceReview } from "@/components/compliance/evidence-review";
import { PageHeader } from "@/components/page-header";
import { PriorityBadge } from "@/components/priority-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { CARD_LINK_FOCUS } from "@/lib/focus";
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

      {/* The number, then what it is made of. "5 decisions" on its own
          is a badge; the breakdown is what lets someone decide whether
          this is ten minutes or an afternoon before they start. */}
      {data && data.total_needing_review > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-[var(--fg-default)]">
            {data.total_needing_review} decision
            {data.total_needing_review === 1 ? "" : "s"} need
            {data.total_needing_review === 1 ? "s" : ""} your attention
          </h2>
          <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-[var(--fg-muted)]">
            {active.map((category) => (
              <li key={category.key}>
                <a
                  href={`#${category.key}`}
                  className="hover:text-[var(--fg-default)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                >
                  <span className="font-medium text-[var(--fg-default)]">
                    {category.count}
                  </span>{" "}
                  {category.label.toLowerCase()}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

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
          // `scroll-mt` keeps the heading clear of the sticky top bar
          // when the summary above links down to it.
          <section key={category.key} id={category.key} className="scroll-mt-24">
            <div className="mb-2 flex flex-wrap items-baseline gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                {category.label}
              </h2>
              <Badge variant="secondary">{category.count}</Badge>
            </div>
            <p className="mb-3 text-sm leading-relaxed text-[var(--fg-muted)]">
              {category.description}
            </p>

            {/* The one category where the decision can be made in place.
                Evidence mappings are the bulk of this queue and each one
                is a yes/no on a quoted passage — sending the reviewer to
                another screen to answer it, and back here for the next,
                is the queue failing at the one job it has. The component
                is the same one Documents uses, citation and all. */}
            {category.key === "evidence_mappings" ? (
              <EvidenceReview />
            ) : (
            <div className="flex flex-col gap-2">
              {category.items.map((item) => (
                <Link key={item.id} href={item.href} className={CARD_LINK_FOCUS}>
                  <Card className="transition-colors hover:border-[var(--border-strong)]">
                    <CardContent className="flex items-start justify-between gap-4 py-4">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-[var(--fg-default)]">
                            {item.title}
                          </span>
                          <PriorityBadge priority={item.priority} />
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
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
