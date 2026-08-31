"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ShieldCheck } from "lucide-react";

import { AuditEventCard } from "@/components/audit/audit-event-card";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

/** The audit trail, for the people who actually read one.
 *
 * This page used to render the stored row: a module chip, the machine
 * action name, `after {"status":"pass"}` and a bare UUID. Everything a
 * compliance manager wants from it — what changed, to what, by whom —
 * was present in the database and absent from the screen.
 *
 * The translation now happens server-side (app/audit/presentation.py) so
 * every surface says the same words. This page arranges them and keeps
 * the raw record one click away, under Technical details.
 */

/** Where an event belongs. Matched against `category` from the server,
 * so a module added later is filterable the day it starts recording. */
const CATEGORIES: { label: string; value: string }[] = [
  { label: "All", value: "" },
  { label: "Compliance", value: "compliance" },
  { label: "Evidence & documents", value: "evidence" },
  { label: "Gaps & remediation", value: "gaps" },
  { label: "Policies", value: "policies" },
  { label: "AI systems", value: "ai_systems" },
  { label: "Privacy", value: "privacy" },
  { label: "Vendors", value: "vendors" },
  { label: "Security", value: "security" },
];

/** Who did it. A separate axis from *what area* — "show me everything
 * Veyntra did on its own last week" is a different question from "show
 * me the privacy events", and folding them into one chip row would make
 * neither answerable. */
const ACTORS: { label: string; value: string }[] = [
  { label: "All actors", value: "" },
  { label: "People", value: "person" },
  { label: "Veyntra AI", value: "ai" },
  { label: "Veyntra System", value: "system" },
  { label: "Integrations", value: "integration" },
];

function Chip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        active
          ? "rounded-full bg-[var(--brand-primary)] px-3 py-1 text-xs font-medium text-[var(--fg-on-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          : "rounded-full border border-[var(--border-default)] px-3 py-1 text-xs text-[var(--fg-muted)] transition-colors hover:bg-[var(--bg-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
      }
    >
      {label}
    </button>
  );
}

export default function AuditLogsPage() {
  const [category, setCategory] = useState("");
  const [actorKind, setActorKind] = useState("");
  const [search, setSearch] = useState("");

  const { data, isLoading, error } = useQuery<AuditEvent[]>({
    queryKey: ["audit-events", category, actorKind, search],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "200" });
      if (actorKind) params.set("actor_kind", actorKind);
      if (search.trim()) params.set("q", search.trim());
      return apiFetch<AuditEvent[]>(`/api/v1/audit-events?${params.toString()}`);
    },
  });

  // Category is applied here rather than as another query parameter:
  // the server already labels each event's category, and filtering a
  // loaded page keeps the chips instant while search and actor — which
  // genuinely change which rows exist — go to the database.
  const events = (data ?? []).filter(
    (event) => !category || event.category === category
  );

  return (
    <div>
      <PageHeader
        title="Audit Logs"
        description="What changed, to what, and who changed it."
      />

      <Card className="mb-5">
        <CardContent className="py-4">
          <p className="flex items-start gap-2 text-sm leading-relaxed text-[var(--fg-muted)]">
            <ShieldCheck
              className="mt-0.5 h-4 w-4 shrink-0 text-[var(--success-600)]"
              aria-hidden="true"
            />
            Audit records are immutable. Veyntra records important human, AI and system actions
            so changes can be traced over time.
          </p>
        </CardContent>
      </Card>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by area">
          {CATEGORIES.map((option) => (
            <Chip
              key={option.value}
              label={option.label}
              active={category === option.value}
              onClick={() => setCategory(option.value)}
            />
          ))}
        </div>

        <div className="relative ml-auto w-full sm:w-80">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--fg-subtle)]"
            aria-hidden="true"
          />
          <Input
            type="search"
            aria-label="Search audit log"
            placeholder="Search by person, control, framework, document or ID"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
      </div>

      <div
        className="mb-5 flex flex-wrap gap-2"
        role="group"
        aria-label="Filter by who performed the action"
      >
        {ACTORS.map((option) => (
          <Chip
            key={option.value}
            label={option.label}
            active={actorKind === option.value}
            onClick={() => setActorKind(option.value)}
          />
        ))}
      </div>

      {isLoading && <p className="text-sm text-[var(--fg-muted)]">Loading…</p>}

      {error && (
        <p className="text-sm text-[var(--critical-600)]">
          {error instanceof ApiError ? error.message : "Could not load the audit trail."}
        </p>
      )}

      {data && events.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">
          {search.trim()
            ? `Nothing in the audit trail matches “${search.trim()}”.`
            : "No events match this filter yet."}
        </p>
      )}

      <ul className="flex flex-col gap-2">
        {events.map((event) => (
          <AuditEventCard key={event.id} event={event} />
        ))}
      </ul>

      {events.length > 0 && (
        <p className="mt-4 text-xs text-[var(--fg-subtle)]">
          Showing {events.length} event{events.length === 1 ? "" : "s"}, most recent first.
        </p>
      )}
    </div>
  );
}
