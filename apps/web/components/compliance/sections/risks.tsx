"use client";

import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Risk } from "@/lib/types";

/** The risk register: what could stop a control from working.
 *
 * Read-only here. Gaps found during assessment become remediation tasks
 * rather than risks — a risk is something the organization chose to
 * record, not something an assessment concluded.
 */
const SCALE: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

function scale(value: string): string {
  return SCALE[value] ?? value;
}

export function RisksSection() {
  const { data: risks } = useQuery<Risk[]>({
    queryKey: ["compliance", "risks"],
    queryFn: () => apiFetch<Risk[]>("/api/v1/compliance/risks"),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Risk register
      </h2>
      {risks?.length === 0 && (
        <EmptyState
          title="No risks recorded"
          description="Record a risk when something could stop a control from working. Deficiencies found during assessment already appear under Remediation."
        />
      )}
      <div className="flex flex-col gap-2">
        {risks?.map((risk) => (
          <Card key={risk.id}>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-6">
              <div className="min-w-0">
                <div className="font-medium text-[var(--fg-default)]">{risk.title}</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {/* Said in words rather than as `likelihood: high` — a
                      field name and its value pasted together is a
                      database row, not a sentence. */}
                  <Badge variant="outline">{scale(risk.likelihood)} likelihood</Badge>
                  <Badge variant="outline">{scale(risk.impact)} impact</Badge>
                </div>
              </div>
              <StatusBadge status={risk.status} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
