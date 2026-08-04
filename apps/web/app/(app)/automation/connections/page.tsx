"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { IntegrationConnection } from "@/lib/types";

export default function AutomationConnectionsPage() {
  const { data: connections } = useQuery<IntegrationConnection[]>({
    queryKey: ["integrations", "connections"],
    queryFn: () => apiFetch<IntegrationConnection[]>("/api/v1/integrations/connections"),
  });

  return (
    <div>
      <PageHeader
        title="Connections"
        description="The same Integration connections managed in Settings → Integrations — shown here because a Webhook connection can be linked directly to a workflow (spec §38)."
      />
      {connections?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">
          No connections yet.{" "}
          <Link href="/settings/integrations" className="underline">
            Create one in Settings
          </Link>
          .
        </p>
      )}
      <div className="flex flex-col gap-2">
        {connections?.map((connection) => (
          <Card key={connection.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">{connection.name}</div>
                <div className="text-xs text-[var(--fg-subtle)]">
                  {connection.connector_key}
                  {connection.linked_workflow_id && (
                    <>
                      {" · linked to "}
                      <Link
                        href={`/automation/workflows/${connection.linked_workflow_id}`}
                        className="hover:underline"
                      >
                        workflow
                      </Link>
                    </>
                  )}
                </div>
              </div>
              <StatusBadge status={connection.status} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
