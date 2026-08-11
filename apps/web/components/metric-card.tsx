import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type MetricStatus = "success" | "warning" | "critical" | "neutral";

const STATUS_DOT: Record<MetricStatus, string> = {
  success: "bg-[var(--success-500)]",
  warning: "bg-[var(--warning-500)]",
  critical: "bg-[var(--critical-500)]",
  neutral: "bg-[var(--gray-300)]",
};

export function MetricCard({
  label,
  value,
  status = "neutral",
  trend,
  comparisonLabel,
  description,
  icon: Icon,
  href,
  className,
}: {
  label: string;
  value: string;
  status?: MetricStatus;
  /** Positive = improving, negative = worsening. Omit if there's nothing to compare against. */
  trend?: number;
  comparisonLabel?: string;
  description?: string;
  icon?: LucideIcon;
  href?: string;
  className?: string;
}) {
  const body = (
    <Card
      className={cn(
        "group relative overflow-hidden transition-[border-color,background-color,box-shadow] duration-[var(--transition-base)]",
        href &&
          "hover:border-[var(--card-glow)] hover:bg-[var(--bg-surface-hover)] hover:shadow-[var(--shadow-glow)]",
        className,
      )}
    >
      {/* Brand sweep along the top edge, revealed on hover for cards that
          navigate. Only linked cards get it — a static metric shouldn't
          advertise an interaction it doesn't have. */}
      {href && (
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-0.5 bg-[image:var(--gradient-brand)] opacity-0 transition-opacity duration-[var(--transition-base)] group-hover:opacity-100 motion-reduce:transition-none"
        />
      )}
      <CardContent className="pt-5">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_DOT[status])} aria-hidden="true" />
            <span className="text-xs font-medium uppercase tracking-wide text-[var(--fg-muted)]">
              {label}
            </span>
          </div>
          {Icon && (
            <Icon
              className="h-4 w-4 text-[var(--fg-subtle)] transition-colors duration-[var(--transition-base)] group-hover:text-[var(--brand-cyan)]"
              aria-hidden="true"
            />
          )}
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold text-[var(--fg-default)]">{value}</span>
          {trend !== undefined && (
            <span
              className={cn(
                "flex items-center gap-0.5 text-xs font-medium",
                trend >= 0 ? "text-[var(--success-600)]" : "text-[var(--critical-600)]",
              )}
            >
              {trend >= 0 ? (
                <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
              ) : (
                <ArrowDownRight className="h-3 w-3" aria-hidden="true" />
              )}
              {Math.abs(trend)}%
            </span>
          )}
        </div>
        {(description ?? comparisonLabel) && (
          <p className="mt-1 text-xs text-[var(--fg-subtle)]">{description ?? comparisonLabel}</p>
        )}
      </CardContent>
    </Card>
  );

  if (href) {
    return (
      <Link href={href} className="block rounded-[var(--radius-lg)]">
        {body}
      </Link>
    );
  }
  return body;
}
