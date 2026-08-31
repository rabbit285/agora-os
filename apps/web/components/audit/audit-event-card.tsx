"use client";

import Link from "next/link";
import { useState } from "react";
import { Bot, Cog, Plug, ShieldQuestion, User } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { AuditActorKind, AuditEvent } from "@/lib/types";

/** One event on the audit timeline.
 *
 * The card answers, in this order: what happened, what it happened to,
 * what changed, who did it, when. That order is deliberate — a
 * compliance manager scanning a page of these is looking for the first
 * two, and the previous design led with a module chip and a machine
 * name, then printed the JSON and a UUID.
 *
 * The raw event has not gone anywhere. It is one click away, under
 * Technical details, because an auditor tracing a specific record needs
 * exactly the fields a normal reader must never be shown by default.
 */

const ACTOR_ICONS: Record<AuditActorKind, typeof User> = {
  person: User,
  ai: Bot,
  system: Cog,
  integration: Plug,
  unknown: ShieldQuestion,
};

/** Never colour alone: each actor kind carries its own icon and its own
 * word, so the distinction survives a greyscale print-out of the trail —
 * which is how an audit log is often actually read. */
const ACTOR_TONES: Record<AuditActorKind, string> = {
  person: "text-[var(--fg-muted)]",
  ai: "text-[var(--ai-600)]",
  system: "text-[var(--fg-muted)]",
  integration: "text-[var(--fg-muted)]",
  unknown: "text-[var(--fg-subtle)]",
};

export function formatTimestamp(iso: string): { absolute: string; relative: string } {
  const when = new Date(iso);
  const absolute = when.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
  return { absolute, relative: relativeTime(when) };
}

/** Secondary to the exact time, never a replacement for it: an audit
 * record that says only "2 days ago" is not one you can cite. */
function relativeTime(when: Date, now: Date = new Date()): string {
  const seconds = Math.round((now.getTime() - when.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months} month${months === 1 ? "" : "s"} ago`;
  const years = Math.round(months / 12);
  return `${years} year${years === 1 ? "" : "s"} ago`;
}

export function AuditEventCard({ event }: { event: AuditEvent }) {
  const { absolute, relative } = formatTimestamp(event.created_at);
  const ActorIcon = ACTOR_ICONS[event.actor_kind] ?? ShieldQuestion;

  return (
    <li className="rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          {/* 1. What happened. */}
          <p className="font-medium text-[var(--fg-default)]">{event.title}</p>

          {/* 2. What it happened to — by name, and clickable where the
              record has a page. */}
          {event.entity && (
            <p className="mt-0.5 text-sm">
              <span className="text-[var(--fg-subtle)]">{event.entity.kind}: </span>
              {event.entity.href ? (
                <Link
                  href={event.entity.href}
                  className="rounded-sm text-[var(--fg-default)] hover:text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                >
                  {event.entity.label}
                </Link>
              ) : (
                <span
                  className={
                    event.entity.available
                      ? "text-[var(--fg-default)]"
                      : "italic text-[var(--fg-subtle)]"
                  }
                >
                  {event.entity.label}
                </span>
              )}
            </p>
          )}
        </div>

        {/* 5. When. Exact, with the relative reading underneath — an
            audit entry that says only "2 days ago" cannot be cited. */}
        <p className="shrink-0 text-right text-xs text-[var(--fg-subtle)]">
          <time dateTime={event.created_at} className="block tabular-nums">
            {absolute}
          </time>
          <span className="block">{relative}</span>
        </p>
      </div>

      {/* 3. What changed. */}
      {event.changes.length > 0 && (
        <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
          {event.changes.map((change) => (
            <div key={change.label} className="flex items-baseline gap-1.5 text-sm">
              <dt className="text-[var(--fg-subtle)]">{change.label}:</dt>
              <dd className="text-[var(--fg-default)]">
                {change.before ? (
                  <>
                    <span className="text-[var(--fg-muted)]">{change.before}</span>
                    <span aria-label="changed to" className="mx-1 text-[var(--fg-subtle)]">
                      →
                    </span>
                    {change.after}
                  </>
                ) : (
                  change.after
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {/* 6. Why, where the person said so. */}
      {event.reason && (
        <p className="mt-2 border-l-2 border-[var(--border-default)] pl-2 text-sm leading-relaxed text-[var(--fg-muted)]">
          <span className="text-[var(--fg-subtle)]">Reason: </span>
          {event.reason}
        </p>
      )}

      {/* 4. Who, and the way into the raw record. */}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <p
          className={`flex items-center gap-1.5 text-sm ${ACTOR_TONES[event.actor_kind] ?? ""}`}
        >
          <ActorIcon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="text-[var(--fg-subtle)]">By</span>
          {event.actor_name}
        </p>
        <TechnicalDetails event={event} />
      </div>
    </li>
  );
}

/** The raw event, on request.
 *
 * Everything the timeline deliberately hides — the action name, both
 * ids, the untouched before/after JSON — lives here. This is not a
 * concession: an auditor tracing one record needs precisely these
 * fields, and the redesign moved them rather than removing them.
 */
function TechnicalDetails({ event }: { event: AuditEvent }) {
  const [open, setOpen] = useState(false);
  const { absolute } = formatTimestamp(event.created_at);

  const rows: { label: string; value: string | null }[] = [
    { label: "Event", value: event.title },
    { label: "Event code", value: event.action },
    { label: "Event ID", value: event.id },
    { label: "Timestamp", value: `${absolute} (${event.created_at})` },
    { label: "Actor", value: event.actor_name },
    { label: "Actor type", value: event.actor_kind },
    { label: "Actor ID", value: event.actor_user_id },
    { label: "Actor email", value: event.actor_email },
    { label: "Entity", value: event.entity ? `${event.entity.kind}: ${event.entity.label}` : null },
    { label: "Entity type", value: event.object_type },
    { label: "Record ID", value: event.object_id },
    { label: "Trace ID", value: event.correlation_id },
    { label: "Reason", value: event.reason },
  ];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger className="rounded-[var(--radius-md)] px-1 text-xs text-[var(--fg-subtle)] underline-offset-2 hover:text-[var(--fg-default)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]">
        Technical details
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{event.title}</DialogTitle>
        </DialogHeader>

        <dl className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
          {rows
            .filter((row) => row.value)
            .map((row) => (
              <div key={row.label} className="contents">
                <dt className="text-[var(--fg-subtle)]">{row.label}</dt>
                <dd className="break-all font-mono text-xs text-[var(--fg-default)]">
                  {row.value}
                </dd>
              </div>
            ))}
        </dl>

        <StateBlock title="Before" state={event.before_state} />
        <StateBlock title="After" state={event.after_state} />

        <p className="mt-2 text-xs leading-relaxed text-[var(--fg-subtle)]">
          This record cannot be edited or deleted, including by an administrator.
        </p>
      </DialogContent>
    </Dialog>
  );
}

function StateBlock({
  title,
  state,
}: {
  title: string;
  state: Record<string, unknown> | null;
}) {
  if (!state || Object.keys(state).length === 0) return null;
  return (
    <div className="mt-3">
      <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
        {title}
      </h3>
      {/* Pretty-printed, and only here. Wide content scrolls inside its
          own box rather than pushing the dialog sideways. */}
      <pre className="max-h-64 overflow-auto rounded-[var(--radius-md)] bg-[var(--bg-app)] p-3 text-xs leading-relaxed text-[var(--fg-muted)]">
        {JSON.stringify(state, null, 2)}
      </pre>
    </div>
  );
}

export function ActorBadge({ kind, name }: { kind: AuditActorKind; name: string }) {
  const Icon = ACTOR_ICONS[kind] ?? ShieldQuestion;
  return (
    <Badge variant="outline" className="gap-1">
      <Icon className="h-3 w-3" aria-hidden="true" />
      {name}
    </Badge>
  );
}
