import { AlertTriangle } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import type { ProviderStatusOut } from "@/lib/types";

const CAPABILITY_LABELS: Record<keyof ProviderStatusOut["capabilities"], string> = {
  company_search: "Company search",
  people_search: "People search",
  company_enrichment: "Company enrichment",
  person_enrichment: "Person enrichment",
  decision_makers: "Decision makers",
  credit_estimation: "Credit estimation",
};

/** Deliberately not the OAuth IntegrationCard — Apollo is a single
 * deployment-wide API key, not a per-organization connection, so there's
 * no Connect/Disconnect/Revoke action here, just an honest read-only
 * status (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §9). */
export function ProviderStatusCard({ provider }: { provider: ProviderStatusOut }) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
        <div>
          <div className="mb-1.5 flex items-center gap-2">
            <span className="text-sm font-semibold capitalize text-[var(--fg-default)]">
              {provider.provider_key}
            </span>
            <StatusBadge status={provider.status} />
          </div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(provider.capabilities)
              .filter(([, enabled]) => enabled)
              .map(([key]) => (
                <span
                  key={key}
                  className="rounded-[var(--radius-sm)] bg-[var(--bg-sunken)] px-1.5 py-0.5 text-[11px] text-[var(--fg-muted)]"
                >
                  {CAPABILITY_LABELS[key as keyof ProviderStatusOut["capabilities"]]}
                </span>
              ))}
          </div>
        </div>
        {!provider.configured && (
          <div className="flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--warning-50)] px-2.5 py-1.5 text-xs text-[var(--warning-700)]">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            Showing labeled demo data. Set APOLLO_API_KEY to search real companies and people.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
