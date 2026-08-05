import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SourceCitation } from "@/components/source-citation";
import { cn } from "@/lib/utils";

/** Shaped for the AI Recommendation Engine (spec §87) and Daily Briefing's AI
 * suggestion — one visual pattern for both. */
export function InsightCard({
  title,
  reason,
  sources,
  confidence,
  suggestedAction,
  actLabel = "Act on this",
  onAct,
  onDismiss,
  isActing,
  isDismissing,
  className,
}: {
  title: string;
  reason: string;
  sources?: string[];
  confidence?: "low" | "medium" | "high";
  suggestedAction?: string;
  actLabel?: string;
  onAct?: () => void;
  onDismiss?: () => void;
  isActing?: boolean;
  isDismissing?: boolean;
  className?: string;
}) {
  return (
    <Card className={cn("border-[var(--ai-100)] bg-[var(--ai-50)]", className)}>
      <CardContent className="pt-5">
        <div className="mb-2 flex items-start justify-between gap-3">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-[var(--ai-600)]" aria-hidden="true" />
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--ai-700)]">
              AI Recommendation
            </span>
          </div>
          {confidence && (
            <Badge variant="ai" className="capitalize">
              {confidence} confidence
            </Badge>
          )}
        </div>
        <p className="mb-1 text-sm font-medium text-[var(--fg-default)]">{title}</p>
        <p className="mb-3 text-xs text-[var(--fg-muted)]">{reason}</p>
        {sources && sources.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {sources.map((source) => (
              <SourceCitation key={source} source={source} />
            ))}
          </div>
        )}
        {suggestedAction && (
          <p className="mb-3 rounded-[var(--radius-sm)] bg-white/60 px-2.5 py-1.5 text-xs text-[var(--fg-default)]">
            <span className="font-medium">Suggested action: </span>
            {suggestedAction}
          </p>
        )}
        {(onAct || onDismiss) && (
          <div className="flex gap-2">
            {onAct && (
              <Button size="sm" variant="ai" disabled={isActing} onClick={onAct}>
                {isActing ? "Working…" : actLabel}
              </Button>
            )}
            {onDismiss && (
              <Button size="sm" variant="ghost" disabled={isDismissing} onClick={onDismiss}>
                Dismiss
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
