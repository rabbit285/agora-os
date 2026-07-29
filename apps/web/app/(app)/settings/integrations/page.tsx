"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { API_URL, apiFetch } from "@/lib/api";
import type { IntegrationConnection, WebhookEvent, Workflow } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

function ConnectionCard({ connection, workflows }: { connection: IntegrationConnection; workflows: Workflow[] | undefined }) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const { data: events } = useQuery<WebhookEvent[]>({
    queryKey: ["integrations", "connections", connection.id, "events"],
    queryFn: () =>
      apiFetch<WebhookEvent[]>(`/api/v1/integrations/connections/${connection.id}/events`),
    enabled: expanded,
  });

  const toggleStatus = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/integrations/connections/${connection.id}`, {
        method: "PATCH",
        body: { status: connection.status === "active" ? "disabled" : "active" },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["integrations", "connections"] }),
  });

  const linkWorkflow = useMutation({
    mutationFn: (workflowId: string) =>
      apiFetch(`/api/v1/integrations/connections/${connection.id}`, {
        method: "PATCH",
        body: workflowId ? { linked_workflow_id: workflowId } : { unlink_workflow: true },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["integrations", "connections"] }),
  });

  const webhookUrl = `${API_URL}/api/v1/integrations/webhooks/${connection.id}/receive`;
  const webhookWorkflows = workflows?.filter((w) => w.trigger_type === "webhook") ?? [];

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium text-neutral-900">{connection.name}</div>
            <div className="text-xs text-neutral-400">{connection.connector_key}</div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={connection.status} />
            <Button size="sm" variant="outline" onClick={() => toggleStatus.mutate()}>
              {connection.status === "active" ? "Disable" : "Enable"}
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-neutral-400">Webhook URL</span>
          <Input readOnly value={webhookUrl} className="font-mono text-xs" />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-neutral-400">
            Secret (HMAC-SHA256 the raw request body, send as X-Webhook-Signature)
          </span>
          <Input readOnly value={connection.webhook_secret} className="font-mono text-xs" />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-neutral-500">Linked workflow:</span>
          <select
            className={selectClassName}
            value={connection.linked_workflow_id ?? ""}
            onChange={(e) => linkWorkflow.mutate(e.target.value)}
          >
            <option value="">Not linked</option>
            {webhookWorkflows.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
          {webhookWorkflows.length === 0 && (
            <span className="text-xs text-neutral-400">
              No workflows with trigger_type=&ldquo;webhook&rdquo; yet.
            </span>
          )}
        </div>

        {connection.last_error && (
          <p className="text-xs text-red-600">Last error: {connection.last_error}</p>
        )}

        <button
          className="self-start text-xs text-neutral-500 hover:underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Hide" : "Show"} received events
        </button>
        {expanded && (
          <div className="flex flex-col gap-1">
            {events?.length === 0 && (
              <p className="text-xs text-neutral-400">No events received yet.</p>
            )}
            {events?.map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between rounded border border-neutral-200 px-2 py-1 text-xs"
              >
                <span>{new Date(event.received_at).toLocaleString()}</span>
                <div className="flex items-center gap-2">
                  {event.triggered_run_id && <span className="text-neutral-400">triggered a run</span>}
                  <StatusBadge status={event.verified ? "succeeded" : "failed"} />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function IntegrationsSettingsPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const { data: connections } = useQuery<IntegrationConnection[]>({
    queryKey: ["integrations", "connections"],
    queryFn: () => apiFetch<IntegrationConnection[]>("/api/v1/integrations/connections"),
  });

  const { data: workflows } = useQuery<Workflow[]>({
    queryKey: ["automation", "workflows"],
    queryFn: () => apiFetch<Workflow[]>("/api/v1/automation/workflows"),
  });

  const createConnection = useMutation({
    mutationFn: () =>
      apiFetch<IntegrationConnection>("/api/v1/integrations/connections", {
        method: "POST",
        body: { name },
      }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["integrations", "connections"] });
    },
  });

  return (
    <div>
      <PageHeader
        title="Integrations"
        description="Generic inbound webhook connector — spec sections 48-49. Every other provider category (CRM, email, cloud, identity, ...) needs real third-party credentials this environment doesn't have."
      />

      <Card className="mb-4">
        <CardContent className="flex gap-2 pt-6">
          <Input
            placeholder="Connection name (e.g. Lead intake)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Button disabled={!name.trim() || createConnection.isPending} onClick={() => createConnection.mutate()}>
            Add webhook connection
          </Button>
        </CardContent>
      </Card>

      {connections?.length === 0 && (
        <p className="text-sm text-neutral-500">No connections yet.</p>
      )}
      <div className="flex flex-col gap-3">
        {connections?.map((connection) => (
          <ConnectionCard key={connection.id} connection={connection} workflows={workflows} />
        ))}
      </div>
    </div>
  );
}
