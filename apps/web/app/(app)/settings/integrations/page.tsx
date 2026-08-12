"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { API_URL, apiFetch } from "@/lib/api";
import type {
  IntegrationConnection,
  OAuthStartResponse,
  ProviderCatalogEntry,
  SyncRun,
  WebhookEvent,
  Workflow,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

const IN_FLIGHT_SYNC_STATUSES = new Set(["running"]);

function WebhookConnectionCard({
  connection,
  workflows,
}: {
  connection: IntegrationConnection;
  workflows: Workflow[] | undefined;
}) {
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
            <div className="font-medium text-[var(--fg-default)]">{connection.name}</div>
            <div className="text-xs text-[var(--fg-subtle)]">{connection.connector_key}</div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={connection.status} />
            <Button size="sm" variant="outline" onClick={() => toggleStatus.mutate()}>
              {connection.status === "active" ? "Disable" : "Enable"}
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">Webhook URL</span>
          <Input readOnly value={webhookUrl} className="font-mono text-xs" />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
            Secret (HMAC-SHA256 the raw request body, send as X-Webhook-Signature)
          </span>
          <Input readOnly value={connection.webhook_secret ?? ""} className="font-mono text-xs" />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-[var(--fg-muted)]">Linked workflow:</span>
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
            <span className="text-xs text-[var(--fg-subtle)]">
              No workflows with trigger_type=&ldquo;webhook&rdquo; yet.
            </span>
          )}
        </div>

        {connection.last_error && (
          <p className="text-xs text-[var(--critical-600)]">Last error: {connection.last_error}</p>
        )}

        <button
          className="self-start text-xs text-[var(--fg-muted)] hover:underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Hide" : "Show"} received events
        </button>
        {expanded && (
          <div className="flex flex-col gap-1">
            {events?.length === 0 && (
              <p className="text-xs text-[var(--fg-subtle)]">No events received yet.</p>
            )}
            {events?.map((event) => (
              <div
                key={event.id}
                className="flex items-center justify-between rounded border border-[var(--border-default)] px-2 py-1 text-xs"
              >
                <span>{new Date(event.received_at).toLocaleString()}</span>
                <div className="flex items-center gap-2">
                  {event.triggered_run_id && (
                    <span className="text-[var(--fg-subtle)]">triggered a run</span>
                  )}
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

function OAuthConnectionCard({ connection }: { connection: IntegrationConnection }) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const { data: syncRuns } = useQuery<SyncRun[]>({
    queryKey: ["integrations", "connections", connection.id, "sync-runs"],
    queryFn: () =>
      apiFetch<SyncRun[]>(`/api/v1/integrations/connections/${connection.id}/sync-runs`),
    enabled: expanded,
    // Sync runs as a durable Temporal workflow (IntegrationSyncWorkflow),
    // not inline — poll while one is still running so "Sync now" reflects
    // the real succeeded/failed outcome without a manual refresh, the same
    // pattern the Knowledge module uses for document ingestion status.
    refetchInterval: (query) => {
      const runs = query.state.data ?? [];
      return runs.some((r) => IN_FLIGHT_SYNC_STATUSES.has(r.status)) ? 2000 : false;
    },
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["integrations", "connections"] });

  const checkHealth = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/integrations/connections/${connection.id}/health`, { method: "POST" }),
    onSuccess: invalidate,
  });

  const refreshToken = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/integrations/connections/${connection.id}/refresh`, { method: "POST" }),
    onSuccess: invalidate,
  });

  const disconnect = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/integrations/connections/${connection.id}/disconnect`, {
        method: "POST",
      }),
    onSuccess: invalidate,
  });

  const sync = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/integrations/connections/${connection.id}/sync`, { method: "POST" }),
    onSuccess: () => {
      invalidate();
      setExpanded(true);
      queryClient.invalidateQueries({
        queryKey: ["integrations", "connections", connection.id, "sync-runs"],
      });
    },
  });

  const isConnected = connection.status === "connected";
  const hasRunningSync = syncRuns?.some((r) => IN_FLIGHT_SYNC_STATUSES.has(r.status)) ?? false;

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium text-[var(--fg-default)]">{connection.name}</div>
            <div className="text-xs text-[var(--fg-subtle)]">
              {connection.connector_key}
              {connection.external_account_id && ` · account ${connection.external_account_id}`}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {connection.health_status && <StatusBadge status={connection.health_status} />}
            <StatusBadge status={connection.status} />
          </div>
        </div>

        {connection.scopes && connection.scopes.length > 0 && (
          <div className="text-xs text-[var(--fg-muted)]">Scopes: {connection.scopes.join(", ")}</div>
        )}

        {connection.last_error && (
          <p className="text-xs text-[var(--critical-600)]">Last error: {connection.last_error}</p>
        )}

        {isConnected && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" disabled={checkHealth.isPending} onClick={() => checkHealth.mutate()}>
              Check health
            </Button>
            <Button size="sm" variant="outline" disabled={refreshToken.isPending} onClick={() => refreshToken.mutate()}>
              Refresh token
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={sync.isPending || hasRunningSync}
              onClick={() => sync.mutate()}
            >
              {hasRunningSync ? "Syncing…" : "Sync now"}
            </Button>
            <Button size="sm" variant="destructive" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
              Disconnect
            </Button>
          </div>
        )}

        <button
          className="self-start text-xs text-[var(--fg-muted)] hover:underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Hide" : "Show"} sync history
        </button>
        {expanded && (
          <div className="flex flex-col gap-1">
            {syncRuns?.length === 0 && (
              <p className="text-xs text-[var(--fg-subtle)]">No syncs run yet.</p>
            )}
            {syncRuns?.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between rounded border border-[var(--border-default)] px-2 py-1 text-xs"
              >
                <div className="flex flex-col">
                  <span>{new Date(run.started_at).toLocaleString()}</span>
                  {run.cursor_used && (
                    <span className="font-mono text-[var(--fg-subtle)]">
                      resumed from checkpoint
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {run.items_synced !== null && (
                    <span className="text-[var(--fg-subtle)]">{run.items_synced} items</span>
                  )}
                  <StatusBadge status={run.status} />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ProviderCatalogSection() {
  const queryClient = useQueryClient();
  const [previewing, setPreviewing] = useState<string | null>(null);

  const { data: providers } = useQuery<ProviderCatalogEntry[]>({
    queryKey: ["integrations", "providers"],
    queryFn: () => apiFetch<ProviderCatalogEntry[]>("/api/v1/integrations/providers"),
  });

  const connect = useMutation({
    mutationFn: (connectorKey: string) =>
      apiFetch<OAuthStartResponse>(`/api/v1/integrations/connections/oauth/${connectorKey}/start`, {
        method: "POST",
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["integrations", "connections"] });
      window.location.href = data.authorization_url;
    },
  });

  const oauthProviders = providers?.filter((p) => p.auth_type === "oauth2") ?? [];

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        OAuth Connectors
      </h2>
      <div className="flex flex-col gap-2">
        {oauthProviders.map((provider) => {
          const isPreviewing = previewing === provider.connector_key;
          return (
            <Card key={provider.connector_key}>
              <CardContent className="flex flex-col gap-3 pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-[var(--fg-default)]">{provider.name}</div>
                    <div className="text-xs text-[var(--fg-subtle)]">
                      {provider.scopes.length} permission
                      {provider.scopes.length === 1 ? "" : "s"} requested
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {provider.configured ? (
                      <Button
                        size="sm"
                        variant={isPreviewing ? "outline" : "default"}
                        disabled={connect.isPending}
                        onClick={() =>
                          setPreviewing(isPreviewing ? null : provider.connector_key)
                        }
                      >
                        {isPreviewing ? "Cancel" : "Connect"}
                      </Button>
                    ) : (
                      <Badge variant="outline">Not configured</Badge>
                    )}
                  </div>
                </div>

                {isPreviewing && (
                  <div className="rounded border border-[var(--border-default)] bg-[var(--bg-sunken)] p-3">
                    <p className="mb-2 text-xs font-medium text-[var(--fg-muted)]">
                      Connecting {provider.name} will request:
                    </p>
                    <ul className="mb-3 flex flex-col gap-1">
                      {provider.scopes.map((scope) => (
                        <li
                          key={scope}
                          className="font-mono text-xs text-[var(--fg-muted)] before:mr-1.5 before:content-['•']"
                        >
                          {scope}
                        </li>
                      ))}
                    </ul>
                    {provider.connector_key === "apollo" && (
                      <div className="mb-3 flex flex-col gap-1 text-xs text-[var(--fg-muted)]">
                        <p>
                          Veyntra will use your organization&rsquo;s Apollo account,
                          permissions, rate limits, and credits for company search and enrichment.
                        </p>
                        <p>
                          Company search and enrichment consume your own Apollo credits. Imported
                          records are visible to users in this organization with Lead Finder access
                          and keep their Apollo provenance. You can disconnect at any time.
                        </p>
                      </div>
                    )}
                    <Button
                      size="sm"
                      disabled={connect.isPending}
                      onClick={() => connect.mutate(provider.connector_key)}
                    >
                      Authorize on {provider.name}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
      {oauthProviders.some((p) => !p.configured) && (
        <p className="mt-2 text-xs text-[var(--fg-subtle)]">
          Set the provider&apos;s client ID/secret in the environment to enable a real connection —
          see .env.example. Without them, &ldquo;Connect&rdquo; is disabled rather than faking a
          connected state.
        </p>
      )}
    </div>
  );
}

export default function IntegrationsSettingsPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [banner] = useState<{ kind: "success" | "error"; text: string } | null>(() => {
    if (typeof window === "undefined") return null;
    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected");
    const error = params.get("error");
    if (connected) return { kind: "success", text: `Connected to ${connected}.` };
    if (error) return { kind: "error", text: error };
    return null;
  });

  useEffect(() => {
    if (banner) {
      window.history.replaceState({}, "", window.location.pathname);
    }
    // Runs once on mount only — banner is derived from the URL at that moment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const webhookConnections = connections?.filter((c) => c.connector_key === "webhook") ?? [];
  const oauthConnections = connections?.filter((c) => c.connector_key !== "webhook") ?? [];

  return (
    <div>
      <PageHeader
        title="Integrations"
        description="Connector SDK backbone — spec sections 48-49. Every provider category needing real third-party credentials this environment doesn't have reports honestly as Not configured, never a fake connected state."
      />

      {banner && (
        <Card className="mb-4">
          <CardContent className="pt-6">
            <p className={banner.kind === "error" ? "text-sm text-[var(--critical-600)]" : "text-sm text-[var(--success-700)]"}>
              {banner.text}
            </p>
          </CardContent>
        </Card>
      )}

      <ProviderCatalogSection />

      {oauthConnections.length > 0 && (
        <div className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
            OAuth Connections
          </h2>
          <div className="flex flex-col gap-3">
            {oauthConnections.map((connection) => (
              <OAuthConnectionCard key={connection.id} connection={connection} />
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Webhook Connections
        </h2>
        <Card className="mb-4">
          <CardContent className="flex gap-2 pt-6">
            <Input
              placeholder="Connection name (e.g. Lead intake)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Button
              disabled={!name.trim() || createConnection.isPending}
              onClick={() => createConnection.mutate()}
            >
              Add webhook connection
            </Button>
          </CardContent>
        </Card>

        {webhookConnections.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">No webhook connections yet.</p>
        )}
        <div className="flex flex-col gap-3">
          {webhookConnections.map((connection) => (
            <WebhookConnectionCard key={connection.id} connection={connection} workflows={workflows} />
          ))}
        </div>
      </div>
    </div>
  );
}
