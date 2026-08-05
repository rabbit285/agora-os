"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { EntityTabs } from "@/components/entity-tabs";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { useCurrentPermissions } from "@/lib/session";
import type { ProviderStatusOut } from "@/lib/types";

import { CompanyWorkspace } from "./company-workspace";
import { PersonWorkspace } from "./person-workspace";
import { ProviderStatusCard } from "./provider-status-card";

export default function LeadFinderPage() {
  const { data: permissions } = useCurrentPermissions();
  const canView = !permissions || permissions.includes("sales.lead_finder.view");

  const { data: providers } = useQuery<ProviderStatusOut[]>({
    queryKey: ["sales", "lead-finder", "providers"],
    queryFn: () => apiFetch<ProviderStatusOut[]>("/api/v1/sales/lead-finder/providers"),
    enabled: canView,
  });

  if (permissions && !canView) {
    return (
      <div>
        <PageHeader title="Lead Finder" description="Company and people discovery." />
        <p className="text-sm text-[var(--fg-muted)]">
          You don&apos;t have permission to view the Lead Finder. Ask a Sales Manager to grant
          &quot;sales.lead_finder.view&quot;.
        </p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Lead Finder"
        description="Search, save, and enrich companies and people — provider-neutral, never fabricated."
        actions={
          <div className="flex gap-2">
            <Link href="/sales/lead-finder/saved-searches">
              <Button variant="outline" size="sm">
                Saved Searches
              </Button>
            </Link>
            <Link href="/sales/lists">
              <Button variant="outline" size="sm">
                Lists
              </Button>
            </Link>
          </div>
        }
      />

      {providers && providers.length > 0 && (
        <div className="mb-4 grid gap-3">
          {providers.map((provider) => (
            <ProviderStatusCard key={provider.provider_key} provider={provider} />
          ))}
        </div>
      )}

      <EntityTabs
        tabs={[
          { value: "companies", label: "Companies", content: <CompanyWorkspace /> },
          { value: "people", label: "People", content: <PersonWorkspace /> },
        ]}
      />
    </div>
  );
}
