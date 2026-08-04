import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { IntegrationConnection, ProviderCatalogEntry } from "@/lib/types";

export type IntegrationStatus =
  | "not_configured"
  | "ready_to_connect"
  | "connected"
  | "syncing"
  | "degraded"
  | "failed"
  | "disabled"
  | "revoked"
  | "demo";

const STATUS_LABEL: Record<IntegrationStatus, string> = {
  not_configured: "Not configured",
  ready_to_connect: "Ready to connect",
  connected: "Connected",
  syncing: "Syncing",
  degraded: "Degraded",
  failed: "Failed",
  disabled: "Disabled",
  revoked: "Revoked",
  demo: "Demo",
};

const STATUS_VARIANT: Record<IntegrationStatus, "secondary" | "success" | "warning" | "destructive" | "outline"> = {
  not_configured: "outline",
  ready_to_connect: "secondary",
  connected: "success",
  syncing: "warning",
  degraded: "warning",
  failed: "destructive",
  disabled: "outline",
  revoked: "destructive",
  demo: "secondary",
};

/** A connector's real status, computed from the real catalog+connection
 * data — never a fabricated "connected" state (spec §82). */
export function deriveIntegrationStatus(
  entry: ProviderCatalogEntry,
  connection: IntegrationConnection | undefined,
): IntegrationStatus {
  if (!entry.configured) return "not_configured";
  if (!connection) return "ready_to_connect";
  if (connection.status === "disabled") return "disabled";
  if (connection.status === "disconnected") return "revoked";
  if (connection.status === "error" || connection.health_status === "error") {
    return connection.last_synced_at ? "degraded" : "failed";
  }
  return "connected";
}

export function IntegrationCard({
  name,
  status,
  purpose,
  scopes,
  writeCapable = false,
  lastSyncedAt,
  lastError,
  onConnect,
  onReconnect,
  onDisable,
  onRevoke,
  onViewAudit,
}: {
  name: string;
  status: IntegrationStatus;
  purpose?: string;
  scopes?: string[];
  writeCapable?: boolean;
  lastSyncedAt?: string | null;
  lastError?: string | null;
  onConnect?: () => void;
  onReconnect?: () => void;
  onDisable?: () => void;
  onRevoke?: () => void;
  onViewAudit?: () => void;
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-[var(--fg-default)]">{name}</span>
          <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABEL[status]}</Badge>
        </div>
        {purpose && <p className="mb-2 text-xs text-[var(--fg-muted)]">{purpose}</p>}
        {scopes && scopes.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {scopes.map((scope) => (
              <span
                key={scope}
                className="rounded-[var(--radius-sm)] bg-[var(--bg-sunken)] px-1.5 py-0.5 text-[11px] font-mono text-[var(--fg-muted)]"
              >
                {scope}
              </span>
            ))}
          </div>
        )}
        <p className="mb-3 text-[11px] text-[var(--fg-subtle)]">
          {writeCapable ? "Can read and write data" : "Read-only access"}
          {lastSyncedAt && ` · Last synced ${new Date(lastSyncedAt).toLocaleString()}`}
        </p>
        {lastError && (
          <p className="mb-3 rounded-[var(--radius-sm)] bg-[var(--critical-50)] px-2 py-1 text-[11px] text-[var(--critical-700)]">
            {lastError}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {status === "not_configured" && (
            <Button size="sm" variant="outline" disabled>
              Not configured
            </Button>
          )}
          {status === "ready_to_connect" && onConnect && (
            <Button size="sm" onClick={onConnect}>
              Connect
            </Button>
          )}
          {(status === "failed" || status === "degraded" || status === "revoked") && onReconnect && (
            <Button size="sm" onClick={onReconnect}>
              Reconnect
            </Button>
          )}
          {status === "connected" && onDisable && (
            <Button size="sm" variant="outline" onClick={onDisable}>
              Disable
            </Button>
          )}
          {(status === "connected" || status === "degraded" || status === "failed") && onRevoke && (
            <Button size="sm" variant="destructive" onClick={onRevoke}>
              Revoke
            </Button>
          )}
          {onViewAudit && (
            <Button size="sm" variant="ghost" onClick={onViewAudit}>
              Audit history
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function integrationStatusLabel(status: IntegrationStatus): string {
  return STATUS_LABEL[status];
}
