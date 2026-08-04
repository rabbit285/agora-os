import { cn } from "@/lib/utils";

export type HealthLevel = "healthy" | "degraded" | "critical" | "unknown";

const HEALTH_DOT: Record<HealthLevel, string> = {
  healthy: "bg-[var(--success-500)]",
  degraded: "bg-[var(--warning-500)]",
  critical: "bg-[var(--critical-500)]",
  unknown: "bg-[var(--gray-300)]",
};

export function HealthIndicator({
  level,
  label,
  className,
}: {
  level: HealthLevel;
  label: string;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs text-[var(--fg-muted)]", className)}>
      <span
        className={cn("h-2 w-2 shrink-0 rounded-full", HEALTH_DOT[level])}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}
