"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, ShieldAlert } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { AIIncidentsSection } from "@/components/compliance/sections/ai-incidents";
import { EmptyState } from "@/components/empty-state";
import { apiFetch } from "@/lib/api";
import type { AIGovernanceOverview } from "@/lib/types";

/** AI Systems as a governance surface, not an asset list.
 *
 * The question an enterprise buyer asks is "which AI systems process our
 * information, and how are they governed" — so every card leads with what
 * is documented and what is outstanding, rather than a name and a vendor.
 *
 * Readiness carries its explanation everywhere it appears. A per-system
 * percentage with nothing behind it invites the reader to treat it as a
 * verdict, and it is not one: it measures what is recorded here, not
 * whether the system is lawful.
 */

const RISK_VARIANT: Record<string, "destructive" | "outline" | "secondary"> = {
  unacceptable: "destructive",
  high: "destructive",
  limited: "outline",
  minimal: "secondary",
};

const PRIORITY_VARIANT: Record<string, "destructive" | "outline" | "secondary"> = {
  high: "destructive",
  medium: "outline",
  low: "secondary",
};

function Stat({ label, value, tone }: { label: string; value: string; tone?: "warning" }) {
  return (
    <div>
      <div
        className={
          tone === "warning"
            ? "text-2xl font-semibold text-[var(--warning-700)]"
            : "text-2xl font-semibold text-[var(--fg-default)]"
        }
      >
        {value}
      </div>
      <div className="text-xs text-[var(--fg-muted)]">{label}</div>
    </div>
  );
}

export default function AISystemsPage() {
  const { data } = useQuery<AIGovernanceOverview>({
    queryKey: ["compliance", "ai-governance"],
    queryFn: () => apiFetch<AIGovernanceOverview>("/api/v1/compliance/ai-systems/governance"),
  });

  return (
    <div>
      <PageHeader
        title="AI Systems"
        description="Every AI system you run, what is documented about it, and what is still outstanding."
      />

      {data && data.total_systems > 0 && (
        <Card className="mb-6">
          <CardContent className="flex flex-wrap items-center gap-8 pt-6">
            <Stat label="AI systems" value={String(data.total_systems)} />
            <Stat
              label="High risk"
              value={String(data.high_risk_systems)}
              tone={data.high_risk_systems > 0 ? "warning" : undefined}
            />
            <Stat
              label="Not yet screened"
              value={String(data.systems_without_screening)}
              tone={data.systems_without_screening > 0 ? "warning" : undefined}
            />
            <Stat
              label="Open actions"
              value={String(data.total_open_actions)}
              tone={data.total_open_actions > 0 ? "warning" : undefined}
            />
          </CardContent>
        </Card>
      )}

      {data?.total_systems === 0 && (
        // Names the distinction rather than leaving it to be inferred.
        // Declaring "we use third-party AI" during onboarding is an
        // organization-level fact and is what puts the EU AI Act in
        // scope; this page is the inventory of individual systems, and
        // which obligations actually bind you depends on each one's role
        // and risk class. Seeing "you use AI" on one screen and "none
        // registered" on another reads as a bug unless the product says
        // they are different questions.
        <EmptyState
          title="No individual AI systems registered yet"
          description="If you told Veyntra during onboarding that you use or build AI, that put the EU AI Act in scope for your organization. Which obligations apply depends on each system's role and risk classification — register them here and Veyntra will work that out per system."
        />
      )}

      <div className="flex flex-col gap-4">
        {(data?.systems ?? []).map((system) => (
          <Card key={system.ai_system_id}>
            <CardContent className="pt-6">
              <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <Link
                    href={`/compliance/ai-systems/${system.ai_system_id}`}
                    className="flex items-center gap-2 font-medium text-[var(--fg-default)] hover:underline"
                  >
                    <Bot className="h-4 w-4 text-[var(--fg-subtle)]" aria-hidden="true" />
                    {system.name}
                  </Link>
                  <p className="mt-1 text-xs text-[var(--fg-subtle)]">
                    {system.vendor ?? "Provider not recorded"}
                    {system.model_name ? ` · ${system.model_name}` : ""}
                    {` · ${system.deployment_status}`}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {system.applicable_regulations.map((regulation) => (
                    <Badge key={regulation} variant="outline">
                      {regulation}
                    </Badge>
                  ))}
                  <Badge variant={RISK_VARIANT[system.risk_classification] ?? "secondary"}>
                    {system.risk_classification} risk
                  </Badge>
                </div>
              </div>

              <div className="mb-3 flex flex-wrap items-baseline gap-4">
                <span className="text-2xl font-semibold text-[var(--fg-default)]">
                  {system.readiness_percent}%
                </span>
                <span className="text-sm leading-relaxed text-[var(--fg-muted)]">
                  {system.explanation}
                </span>
              </div>

              {!system.has_current_screening && (
                <p className="mb-3 flex items-center gap-1.5 text-sm text-[var(--warning-700)]">
                  <ShieldAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  Not yet screened under the EU AI Act, so its risk classification has not been
                  established from how it is actually used.
                </p>
              )}

              {system.required_actions.length > 0 ? (
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                    Required actions
                  </h3>
                  <ul className="flex flex-col gap-2">
                    {system.required_actions.map((action) => (
                      <li key={action.title} className="flex items-start gap-2">
                        <AlertTriangle
                          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--warning-700)]"
                          aria-hidden="true"
                        />
                        <span className="text-sm leading-relaxed">
                          <span className="text-[var(--fg-default)]">{action.title}</span>
                          <span className="text-[var(--fg-muted)]"> — {action.detail}</span>
                          {/* Every action names the obligation behind it,
                              so nobody is asked to do work they cannot
                              trace to a requirement. */}
                          <Badge
                            variant={PRIORITY_VARIANT[action.priority] ?? "secondary"}
                            className="ml-2 align-middle"
                          >
                            {action.basis}
                          </Badge>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="flex items-center gap-1.5 text-sm text-[var(--success-700)]">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Nothing outstanding on this system.
                </p>
              )}

              {(system.open_risk_count > 0 || system.open_incident_count > 0) && (
                <p className="mt-3 text-xs text-[var(--fg-subtle)]">
                  {system.open_risk_count} open risk
                  {system.open_risk_count === 1 ? "" : "s"} · {system.open_incident_count} open
                  incident{system.open_incident_count === 1 ? "" : "s"}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
      <AIIncidentsSection />
    </div>
  );
}
