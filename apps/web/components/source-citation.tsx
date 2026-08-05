import { FileText } from "lucide-react";

import { cn } from "@/lib/utils";

/** A single evidence/source reference chip — used by Copilot citations and
 * AI Recommendation `sources` (e.g. "control:<uuid>", "lead:<uuid>"). */
export function SourceCitation({ source, className }: { source: string; className?: string }) {
  const [kind, id] = source.includes(":") ? source.split(/:(.+)/) : [source, undefined];
  const label = kind.replace(/_/g, " ");
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-1.5 py-0.5 text-[11px] text-[var(--fg-muted)]",
        className,
      )}
      title={source}
    >
      <FileText className="h-3 w-3" aria-hidden="true" />
      <span className="capitalize">{label}</span>
      {id && <span className="font-mono text-[var(--fg-subtle)]">{id.slice(0, 8)}</span>}
    </span>
  );
}
