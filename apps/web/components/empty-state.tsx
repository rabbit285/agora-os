import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-[var(--radius-lg)] border border-dashed border-[var(--border-default)] px-6 py-12 text-center",
        className,
      )}
    >
      <Icon className="h-8 w-8 text-[var(--fg-subtle)]" aria-hidden="true" />
      <p className="text-sm font-medium text-[var(--fg-default)]">{title}</p>
      {description && <p className="max-w-sm text-xs text-[var(--fg-muted)]">{description}</p>}
      {action && (
        <Button size="sm" variant="outline" className="mt-2" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
