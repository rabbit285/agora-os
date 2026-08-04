"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Briefing } from "@/lib/types";

function SectionCard({ section }: { section: Briefing["sections"][number] }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 pt-6">
        <h3 className="text-sm font-semibold text-neutral-900">{section.label}</h3>
        <p className="text-sm text-neutral-700">{section.headline}</p>
        {section.items.length > 0 && (
          <ul className="flex flex-col gap-1">
            {section.items.map((item, index) =>
              item.link ? (
                <li key={index}>
                  <Link href={item.link} className="text-xs text-neutral-500 hover:underline">
                    {item.text}
                  </Link>
                </li>
              ) : (
                <li key={index} className="text-xs text-neutral-500">
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
  const { data: briefing, isLoading } = useQuery<Briefing>({
    queryKey: ["briefing"],
    queryFn: () => apiFetch<Briefing>("/api/v1/briefing"),
  });

  return (
    <div>
      <PageHeader
        title="Daily Briefing"
        description={
          briefing
            ? `spec §88 — generated for ${briefing.briefing_date}, from your own live Compliance/Security/Sales/Support/Automation data. Stable for the rest of today.`
            : "spec §88 — real business-data briefing, generated once per day."
        }
      />

      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}

      {briefing?.ai_suggestion && (
        <Card className="mb-4 border-neutral-900">
          <CardContent className="pt-6">
            <p className="text-xs font-medium uppercase text-neutral-400">AI suggestion</p>
            <p className="mt-1 text-sm text-neutral-800">{briefing.ai_suggestion}</p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {briefing?.sections.map((section) => (
          <SectionCard key={section.key} section={section} />
        ))}
      </div>
    </div>
  );
}
