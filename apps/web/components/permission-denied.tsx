import { Lock } from "lucide-react";

import { cn } from "@/lib/utils";

export function PermissionDenied({
  message = "You don't have permission to view this.",
  className,
}: {
  message?: string;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-sunken)] px-6 py-10 text-center",
        className,
      )}
    >
      <Lock className="h-6 w-6 text-[var(--fg-subtle)]" aria-hidden="true" />
      <p className="text-sm font-medium text-[var(--fg-default)]">Access restricted</p>
      <p className="max-w-sm text-xs text-[var(--fg-muted)]">{message}</p>
    </div>
  );
}
