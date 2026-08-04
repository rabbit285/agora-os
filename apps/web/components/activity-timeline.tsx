import { Clock } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { cn } from "@/lib/utils";

export type ActivityEntry = {
  id: string;
  label: string;
  description?: string;
  timestamp: string;
  actorLabel?: string;
};

/** One chronological event list, reused by every detail page's audit
 * history / activity tab — pages map their own data (AuditEvent, a Task's
 * activity feed, a Security incident's Timeline entries) into this shape. */
export function ActivityTimeline({
  entries,
  emptyLabel = "No activity recorded yet.",
  className,
}: {
  entries: ActivityEntry[] | undefined;
  emptyLabel?: string;
  className?: string;
}) {
  if (!entries || entries.length === 0) {
    return <EmptyState icon={Clock} title={emptyLabel} />;
  }

  return (
    <ol className={cn("flex flex-col gap-0", className)}>
      {entries.map((entry, index) => (
        <li key={entry.id} className="relative flex gap-3 pb-4 last:pb-0">
          <div className="flex flex-col items-center">
            <span
              className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[var(--brand-primary)]"
              aria-hidden="true"
            />
            {index < entries.length - 1 && (
              <span className="w-px flex-1 bg-[var(--border-default)]" aria-hidden="true" />
            )}
          </div>
          <div className="pb-1">
            <p className="text-sm text-[var(--fg-default)]">{entry.label}</p>
            {entry.description && (
              <p className="mt-0.5 text-xs text-[var(--fg-muted)]">{entry.description}</p>
            )}
            <p className="mt-0.5 text-[11px] text-[var(--fg-subtle)]">
              {new Date(entry.timestamp).toLocaleString()}
              {entry.actorLabel && ` · ${entry.actorLabel}`}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
