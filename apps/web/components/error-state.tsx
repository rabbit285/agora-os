import { AlertTriangle, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ErrorState({
  title = "Something went wrong",
  description,
  onRetry,
  className,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-[var(--radius-lg)] border border-[var(--critical-50)] bg-[var(--critical-50)] px-6 py-10 text-center",
        className,
      )}
    >
      <AlertTriangle className="h-6 w-6 text-[var(--critical-600)]" aria-hidden="true" />
      <p className="text-sm font-medium text-[var(--critical-700)]">{title}</p>
      {description && <p className="max-w-sm text-xs text-[var(--critical-600)]">{description}</p>}
      {onRetry && (
        <Button size="sm" variant="outline" className="mt-2 gap-1.5" onClick={onRetry}>
          <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
          Try again
        </Button>
      )}
    </div>
  );
}
