"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, ShieldCheck } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { ProviderStatusOut } from "@/lib/types";

const CAPABILITY_LABELS: Record<keyof ProviderStatusOut["capabilities"], string> = {
  company_search: "Company search",
  people_search: "People search",
  company_enrichment: "Company enrichment",
  person_enrichment: "Person enrichment",
  decision_makers: "Decision makers",
  credit_estimation: "Credit estimation",
};

/** Apollo is a per-organization OAuth connection: each customer connects
 * its own Apollo workspace and Agora Origin uses that account's
 * permissions, rate limits, and credits (see
 * docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md). This card therefore shows
 * real connection state and a Connect action for authorized users, rather
 * than the read-only deployment-wide status it showed when Apollo was a
 * single shared API key. */
export function ProviderStatusCard({ provider }: { provider: ProviderStatusOut }) {
  const [previewOpen, setPreviewOpen] = useState(false);

  const startConnect = useMutation({
    mutationFn: () =>
      apiFetch<{ connection_id: string; authorization_url: string }>(
        "/api/v1/integrations/connections/oauth/apollo/start",
        { method: "POST" },
      ),
    onSuccess: (data) => {
      window.location.href = data.authorization_url;
    },
  });

  const isConnected = provider.configured;
  const needsReauthorization = provider.status === "revoked";

  return (
    <Card>
      <CardContent className="flex flex-wrap items-start justify-between gap-3 py-4">
        <div>
          <div className="mb-1.5 flex items-center gap-2">
            <span className="text-sm font-semibold capitalize text-[var(--fg-default)]">
              {provider.provider_key}
            </span>
            <StatusBadge status={provider.status} />
          </div>

          {isConnected && provider.connected_user_email && (
            <p className="mb-1.5 text-xs text-[var(--fg-muted)]">
              Connected as {provider.connected_user_email}
              {provider.connected_workspace_name ? ` · ${provider.connected_workspace_name}` : ""}
            </p>
          )}

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

        <div className="flex flex-col items-end gap-2">
          {needsReauthorization && (
            <div className="flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--warning-50)] px-2.5 py-1.5 text-xs text-[var(--warning-700)]">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              Apollo access needs to be authorized again.
            </div>
          )}

          {!isConnected && !needsReauthorization && (
            <div className="flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--warning-50)] px-2.5 py-1.5 text-xs text-[var(--warning-700)]">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {provider.status === "not_configured"
                ? "Showing labeled demo data. Apollo is not available in this deployment yet."
                : "Showing labeled demo data. Connect Apollo to search real companies and people."}
            </div>
          )}

          {!isConnected && provider.status !== "not_configured" && (
            <>
              {provider.can_manage_connection ? (
                <Button size="sm" onClick={() => setPreviewOpen((open) => !open)}>
                  Connect Apollo
                </Button>
              ) : (
                <p className="text-xs text-[var(--fg-muted)]">
                  Contact your administrator to connect Apollo.
                </p>
              )}
            </>
          )}
        </div>

        {previewOpen && (
          <div className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-sunken)] p-4">
            <div className="mb-2 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
              <h4 className="text-sm font-semibold text-[var(--fg-default)]">
                Connect your Apollo workspace
              </h4>
            </div>
            <p className="mb-3 text-xs text-[var(--fg-muted)]">
              Agora Origin will use your organization&rsquo;s Apollo account, permissions, rate
              limits, and credits for company search and enrichment.
            </p>
            <ul className="mb-3 list-disc space-y-1 pl-5 text-xs text-[var(--fg-muted)]">
              <li>Requested Apollo permissions: {provider.granted_scopes.length > 0 ? provider.granted_scopes.join(", ") : "company search, people search, enrichment, usage statistics, and your Apollo profile"}</li>
              <li>Search and enrichment consume your own Apollo credits.</li>
              <li>Imported companies and people are visible to users in this organization with Lead Finder access.</li>
              <li>You can disconnect at any time from Settings → Integrations.</li>
              <li>Every imported record keeps its Apollo provenance.</li>
            </ul>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => startConnect.mutate()}
                disabled={startConnect.isPending}
              >
                {startConnect.isPending ? "Redirecting…" : "Continue to Apollo"}
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setPreviewOpen(false)}>
                Cancel
              </Button>
            </div>
            {startConnect.isError && (
              <p className="mt-2 text-xs text-[var(--danger-600)]">
                Could not start the Apollo connection. Please try again.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
