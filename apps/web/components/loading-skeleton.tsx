import { cn } from "@/lib/utils";

function Block({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-[var(--radius-sm)] bg-[var(--bg-sunken)]", className)}
    />
  );
}

/** Generic skeleton for a page still loading its primary query. Pass
 * `rows` for a table-shaped skeleton, or `lines` for a text-shaped one. */
export function LoadingSkeleton({
  rows,
  lines = 3,
  className,
}: {
  rows?: number;
  lines?: number;
  className?: string;
}) {
  if (rows !== undefined) {
    return (
      <div className={cn("flex flex-col gap-2", className)} aria-hidden="true">
        {Array.from({ length: rows }).map((_, i) => (
          <Block key={i} className="h-11 w-full" />
        ))}
      </div>
    );
  }
  return (
    <div className={cn("flex flex-col gap-2", className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Block key={i} className={i === lines - 1 ? "h-4 w-2/3" : "h-4 w-full"} />
      ))}
    </div>
  );
}

export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-5",
        className,
      )}
      aria-hidden="true"
    >
      <Block className="mb-3 h-4 w-1/3" />
      <Block className="mb-2 h-6 w-1/2" />
      <Block className="h-3 w-2/3" />
    </div>
  );
}
