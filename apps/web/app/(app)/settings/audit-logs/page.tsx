"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

/** Common starting points. The trail is queried by action prefix rather
 * than by a fixed category list, so a module added later is filterable
 * the day it starts recording events — no registry to keep in step. */
const FILTERS: { label: string; prefix: string }[] = [
  { label: "Everything", prefix: "" },
  { label: "Compliance", prefix: "compliance." },
  { label: "Gaps & remediation", prefix: "compliance.gap" },
  { label: "DSARs", prefix: "compliance.dsar" },
  { label: "Vendors", prefix: "compliance.vendor" },
  { label: "AI systems", prefix: "compliance.ai_system" },
  { label: "Trust Center", prefix: "trust_center" },
  { label: "Billing", prefix: "billing." },
  { label: "Security", prefix: "security." },
];

function humanizeAction(action: string): string {
  const [, ...rest] = action.split(".");
  return rest.join(" ").replace(/_/g, " ") || action;
}

function moduleOf(action: string): string {
  return action.split(".")[0] ?? "";
}

export default function AuditLogsPage() {
  const [prefix, setPrefix] = useState("");
  const [objectId, setObjectId] = useState("");

  const { data, isLoading, error } = useQuery<AuditEvent[]>({
    queryKey: ["audit-events", prefix, objectId],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "200" });
      if (prefix) params.set("action_prefix", prefix);
      if (objectId.trim()) params.set("object_id", objectId.trim());
      return apiFetch<AuditEvent[]>(`/api/v1/audit-events?${params.toString()}`);
    },
  });

  return (
    <div>
      <PageHeader
        title="Audit Logs"
        description="Who did what, and when. Records are append-only — they cannot be edited or deleted after the fact, including by an administrator."
      />

      <Card className="mb-6">
        <CardContent className="pt-6">
          <p className="flex items-start gap-2 text-sm leading-relaxed text-[var(--fg-muted)]">
            <ShieldCheck
              className="mt-0.5 h-4 w-4 shrink-0 text-[var(--success-600)]"
              aria-hidden="true"
            />
            Entries are written as a side effect of the action they describe, and the database
            rejects any attempt to change or remove one. There is no API for creating an entry
            directly — an endpoint that allowed it would allow forging history.
          </p>
        </CardContent>
      </Card>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {FILTERS.map((filter) => (
          <button
            key={filter.label}
            type="button"
            onClick={() => setPrefix(filter.prefix)}
            className={
              prefix === filter.prefix
                ? "rounded-full bg-[var(--brand-primary)] px-3 py-1 text-xs font-medium text-[var(--fg-on-primary)]"
                : "rounded-full border border-[var(--border-default)] px-3 py-1 text-xs text-[var(--fg-muted)] transition-colors hover:bg-[var(--bg-surface-hover)]"
            }
          >
            {filter.label}
          </button>
        ))}
        <Input
          placeholder="Trace one record by id"
          value={objectId}
          onChange={(e) => setObjectId(e.target.value)}
          className="ml-auto max-w-xs"
        />
      </div>

      {isLoading && <p className="text-sm text-[var(--fg-muted)]">Loading…</p>}

      {error && (
        <p className="text-sm text-[var(--critical-600)]">
          {error instanceof ApiError
            ? error.message
            : "Could not load the audit trail."}
        </p>
      )}

      {data?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">
          No events match this filter yet.
        </p>
      )}

      <div className="flex flex-col gap-2">
        {data?.map((event) => (
          <Card key={event.id}>
            <CardContent className="pt-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{moduleOf(event.action)}</Badge>
                  <span className="font-medium text-[var(--fg-default)]">
                    {humanizeAction(event.action)}
                  </span>
                  <span className="text-xs text-[var(--fg-subtle)]">{event.object_type}</span>
                </div>
                <span className="text-xs tabular-nums text-[var(--fg-subtle)]">
                  {new Date(event.created_at).toLocaleString()}
                </span>
              </div>

              {(event.before_state || event.after_state) && (
                <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-[var(--fg-muted)]">
                  {event.before_state && (
                    <span>
                      <span className="text-[var(--fg-subtle)]">before</span>{" "}
                      {JSON.stringify(event.before_state)}
                    </span>
                  )}
                  {event.after_state && (
                    <span>
                      <span className="text-[var(--fg-subtle)]">after</span>{" "}
                      {JSON.stringify(event.after_state)}
                    </span>
                  )}
                </div>
              )}

              {event.object_id && (
                <p className="mt-1 font-mono text-[11px] text-[var(--fg-subtle)]">
                  {event.object_id}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
