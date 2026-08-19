"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Bot, CheckCircle2, Sparkles } from "lucide-react";

import { DashboardHero } from "@/components/dashboard-hero";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { ComplianceDashboard } from "@/lib/types";

/** The executive view.
 *
 * Written for someone accountable for compliance who does not work in it
 * daily — a founder answering an enterprise buyer this week. That reader
 * is badly served by a table of controls and worse served by a single
 * percentage with nothing behind it, so every figure here either links
 * through to what it counts or carries its own arithmetic.
 */

const PRIORITY_VARIANT: Record<string, "destructive" | "outline" | "secondary"> = {
  high: "destructive",
  medium: "outline",
  low: "secondary",
};

function Metric({
  label,
  value,
  href,
  tone,
}: {
  label: string;
  value: number | string;
  href: string;
  tone?: "warning";
}) {
  return (
    <Link href={href} className="min-w-[7rem] flex-1">
      <div className="rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 transition-colors hover:border-[var(--border-strong)]">
        <div
          className={
            tone === "warning"
              ? "text-2xl font-semibold text-[var(--warning-700)]"
              : "text-2xl font-semibold text-[var(--fg-default)]"
          }
        >
          {value}
        </div>
        <div className="mt-0.5 text-xs text-[var(--fg-muted)]">{label}</div>
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const { data } = useQuery<ComplianceDashboard>({
    queryKey: ["compliance", "dashboard"],
    queryFn: () => apiFetch<ComplianceDashboard>("/api/v1/compliance/dashboard"),
  });

  return (
    <div className="flex flex-col gap-6">
      <DashboardHero
        title="Compliance Overview"
        description="Where you stand, what needs attention, and what to do next."
      />

      {data && (
        <>
          <Card>
            <CardContent className="pt-6">
              <div className="flex flex-wrap items-baseline gap-4">
                <span className="text-4xl font-semibold text-[var(--fg-default)]">
                  {data.readiness_percent}%
                </span>
                <span className="text-sm font-medium text-[var(--fg-muted)]">
                  Compliance readiness
                </span>
              </div>
              {/* The number never stands alone. */}
              <p className="mt-2 text-sm leading-relaxed text-[var(--fg-muted)]">
                {data.readiness_explanation}
              </p>
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-3">
            <Metric
              label="Critical gaps"
              value={data.critical_gap_count}
              href="/compliance"
              tone={data.critical_gap_count > 0 ? "warning" : undefined}
            />
            <Metric
              label="Open risks"
              value={data.open_risk_count}
              href="/compliance#controls"
              tone={data.open_risk_count > 0 ? "warning" : undefined}
            />
            <Metric label="AI systems" value={data.ai_system_count} href="/ai-systems" />
            <Metric
              label="High-risk AI"
              value={data.high_risk_ai_system_count}
              href="/ai-systems"
              tone={data.high_risk_ai_system_count > 0 ? "warning" : undefined}
            />
            <Metric
              label="Overdue actions"
              value={data.overdue_action_count}
              href="/tasks"
              tone={data.overdue_action_count > 0 ? "warning" : undefined}
            />
          </div>

          {data.recommended_next_actions.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                What to do next
              </h2>
              <div className="flex flex-col gap-2">
                {data.recommended_next_actions.map((action, index) => (
                  <Link key={`${action.title}-${index}`} href={action.href}>
                    <Card className="transition-colors hover:border-[var(--border-strong)]">
                      <CardContent className="flex items-start justify-between gap-4 py-4">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium text-[var(--fg-default)]">
                              {action.title}
                            </span>
                            <Badge variant={PRIORITY_VARIANT[action.priority] ?? "secondary"}>
                              {action.priority}
                            </Badge>
                          </div>
                          <p className="mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">
                            {action.detail}
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
          )}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                Framework status
              </h2>
              {data.frameworks.length === 0 ? (
                <Card>
                  <CardContent className="pt-6 text-sm text-[var(--fg-muted)]">
                    No framework adopted yet.
                  </CardContent>
                </Card>
              ) : (
                <div className="flex flex-col gap-2">
                  {data.frameworks.map((framework) => (
                    <Link
                      key={framework.framework_id}
                      href={`/compliance/frameworks/${framework.framework_id}`}
                    >
                      <Card className="transition-colors hover:border-[var(--border-strong)]">
                        <CardContent className="py-4">
                          <div className="flex flex-wrap items-baseline justify-between gap-2">
                            <span className="font-medium text-[var(--fg-default)]">
                              {framework.name}
                            </span>
                            <span className="text-xl font-semibold text-[var(--fg-default)]">
                              {framework.readiness_percent}%
                            </span>
                          </div>
                          {framework.open_gap_count > 0 && (
                            <p className="mt-1 text-xs text-[var(--warning-700)]">
                              {framework.open_gap_count} open gap
                              {framework.open_gap_count === 1 ? "" : "s"}
                            </p>
                          )}
                        </CardContent>
                      </Card>
                    </Link>
                  ))}
                </div>
              )}
            </section>

            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                Recent AI activity
              </h2>
              <Card>
                <CardContent className="pt-6">
                  {data.recent_activity.length === 0 ? (
                    <p className="text-sm text-[var(--fg-muted)]">
                      Nothing in the last 7 days.
                    </p>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {data.recent_activity.map((line) => (
                        <li
                          key={line.label}
                          className="flex items-start gap-2 text-sm text-[var(--fg-muted)]"
                        >
                          <Sparkles
                            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--brand-primary)]"
                            aria-hidden="true"
                          />
                          <span>
                            <span className="font-medium text-[var(--fg-default)]">
                              {line.count}
                            </span>{" "}
                            {line.label}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {/* Counted from the audit trail, not narrated — the panel
                      cannot claim work that did not happen. */}
                  <p className="mt-3 text-xs text-[var(--fg-subtle)]">
                    Counted from your audit trail over the last 7 days.
                  </p>
                </CardContent>
              </Card>
            </section>
          </div>

          {data.systems_at_risk.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                AI systems needing attention
              </h2>
              <div className="flex flex-col gap-2">
                {data.systems_at_risk.map((system) => (
                  <Link key={system.ai_system_id} href="/ai-systems">
                    <Card className="transition-colors hover:border-[var(--border-strong)]">
                      <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
                        <span className="flex items-center gap-2 font-medium text-[var(--fg-default)]">
                          <Bot className="h-4 w-4 text-[var(--fg-subtle)]" aria-hidden="true" />
                          {system.name}
                        </span>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline">{system.risk_classification} risk</Badge>
                          <span className="text-sm text-[var(--fg-muted)]">
                            {system.open_action_count} action
                            {system.open_action_count === 1 ? "" : "s"} ·{" "}
                            {system.readiness_percent}%
                          </span>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {data.critical_issues.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                Critical issues
              </h2>
              <div className="flex flex-col gap-2">
                {data.critical_issues.map((issue, index) => (
                  <Card key={`${issue.title}-${index}`}>
                    <CardContent className="flex items-start gap-2.5 py-4">
                      <AlertTriangle
                        className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-700)]"
                        aria-hidden="true"
                      />
                      <div>
                        <p className="text-sm leading-relaxed text-[var(--fg-default)]">
                          {issue.title}
                        </p>
                        <p className="mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">
                          {issue.detail}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </section>
          )}

          {data.critical_gap_count === 0 &&
            data.recommended_next_actions.length === 0 &&
            data.frameworks.length > 0 && (
              <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3 text-sm text-[var(--fg-muted)]">
                <CheckCircle2
                  className="h-4 w-4 text-[var(--success-600)]"
                  aria-hidden="true"
                />
                Nothing needs your attention right now.
              </div>
            )}
        </>
      )}
    </div>
  );
}
