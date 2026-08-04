"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { InsightCard } from "@/components/insight-card";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Briefing } from "@/lib/types";

function SectionCard({ section }: { section: Briefing["sections"][number] }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 pt-5">
        <h3 className="text-sm font-semibold text-[var(--fg-default)]">{section.label}</h3>
        <p className="text-sm text-[var(--fg-muted)]">{section.headline}</p>
        {section.items.length > 0 && (
          <ul className="flex flex-col gap-1">
            {section.items.map((item, index) =>
              item.link ? (
                <li key={index}>
                  <Link
                    href={item.link}
                    className="text-xs text-[var(--fg-subtle)] hover:text-[var(--brand-primary)] hover:underline"
                  >
                    {item.text}
                  </Link>
                </li>
              ) : (
                <li key={index} className="text-xs text-[var(--fg-subtle)]">
                  {item.text}
                </li>
              ),
            )}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function BriefingPage() {
  const { data: briefing, isLoading, error, refetch } = useQuery<Briefing>({
    queryKey: ["briefing"],
    queryFn: () => apiFetch<Briefing>("/api/v1/briefing"),
  });

  return (
    <div>
      <PageHeader
        title="Daily Briefing"
        description={
          briefing
            ? `Generated for ${briefing.briefing_date}, from your own live Compliance/Security/Sales/Support/Automation data. Stable for the rest of today.`
            : "Real business-data briefing, generated once per day."
        }
      />

      {isLoading && <LoadingSkeleton rows={3} />}
      {error && <ErrorState onRetry={() => refetch()} />}

      {briefing?.ai_suggestion && (
        <InsightCard title="Today's AI suggestion" reason={briefing.ai_suggestion} className="mb-4" />
      )}

      {briefing && briefing.sections.length === 0 && (
        <EmptyState title="No briefing sections yet" description="Check back once your modules have data." />
      )}

      {briefing && briefing.sections.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {briefing.sections.map((section) => (
            <SectionCard key={section.key} section={section} />
          ))}
        </div>
      )}
    </div>
  );
}
