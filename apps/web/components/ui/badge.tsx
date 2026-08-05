import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-[var(--radius-sm,0.25rem)] border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "border-transparent bg-[var(--gray-900)] text-white",
        secondary: "border-transparent bg-[var(--gray-100)] text-[var(--gray-700)]",
        success: "border-transparent bg-[var(--success-50)] text-[var(--success-700)]",
        warning: "border-transparent bg-[var(--warning-50)] text-[var(--warning-700)]",
        destructive: "border-transparent bg-[var(--critical-50)] text-[var(--critical-700)]",
        info: "border-transparent bg-[var(--info-50)] text-[var(--info-700)]",
        ai: "border-transparent bg-[var(--ai-100)] text-[var(--ai-700)]",
        outline: "border-[var(--border-strong)] text-[var(--fg-muted)]",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
