import { Bot, ShieldCheck, TrendingUp, Workflow } from "lucide-react";

import { MetricCard } from "@/components/metric-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** The hero's product preview — built from the application's own real
 * components (MetricCard is the literal component the authenticated
 * dashboard uses), not a commissioned illustration or a screenshot of
 * real customer data. Every value here is clearly, persistently labeled
 * as demo data (docs/PUBLIC_SITE_DESIGN.md §10) — nothing here is
 * presented as a real customer outcome. */
export function ProductPreview() {
  return (
    <div className="relative">
      <Card className="overflow-hidden shadow-[var(--shadow-token-md)]">
        <CardHeader className="flex-row items-center justify-between border-b border-[var(--border-default)] pb-3">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm">Command Center</CardTitle>
            <Badge variant="outline">Demo data</Badge>
          </div>
          <span className="text-xs text-[var(--fg-muted)]">Acme AI Technologies</span>
        </CardHeader>
        {/* Neither `description`/`comparisonLabel` nor `trend` is passed to
            any card here: both render with MetricCard's own --fg-subtle /
            --success-600-on-white styling, real but pre-existing contrast
            shortfalls (2.56:1 and 3.76:1 respectively) in a component
            shared across the entire authenticated app — out of scope to
            change for this effort (see docs/PUBLIC_SITE_DESIGN.md). This
            preview reads perfectly well as label + value + status dot
            without either. */}
        <CardContent className="grid gap-3 pt-4 sm:grid-cols-2">
          <MetricCard label="Compliance readiness" value="86%" status="success" icon={ShieldCheck} />
          <MetricCard label="Security posture" value="12 open" status="warning" />
          <MetricCard label="Sales pipeline" value="€184k" status="success" icon={TrendingUp} />
          <MetricCard label="Automation runs" value="342" status="neutral" icon={Workflow} />
        </CardContent>
        <div className="border-t border-[var(--border-default)] bg-[var(--bg-sunken)] p-4">
          <div className="flex items-start gap-2.5 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
            <Bot className="mt-0.5 h-4 w-4 shrink-0 text-[var(--ai-600)]" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-xs font-medium text-[var(--fg-default)]">AI Copilot</p>
              <p className="mt-0.5 text-xs leading-relaxed text-[var(--fg-muted)]">
                &ldquo;2 DPIAs are due for review this week and a security finding on the payments
                service is unresolved for 6 days. Want me to draft remediation tasks for
                approval?&rdquo;
              </p>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
