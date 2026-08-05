import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

export type AuthAlertVariant = "error" | "warning" | "info" | "success";

const VARIANT_STYLE: Record<AuthAlertVariant, { icon: typeof Info; classes: string }> = {
  error: { icon: XCircle, classes: "border-[var(--critical-200,var(--critical-50))] bg-[var(--critical-50)] text-[var(--critical-700)]" },
  warning: { icon: AlertTriangle, classes: "bg-[var(--warning-50)] text-[var(--warning-700)]" },
  info: { icon: Info, classes: "bg-[var(--info-50)] text-[var(--info-700)]" },
  success: { icon: CheckCircle2, classes: "bg-[var(--success-50)] text-[var(--success-700)]" },
};

/** Every auth page's error/success/rate-limited/disabled-account messaging
 * routes through this one component so the visual treatment is
 * consistent — role="alert" so assistive tech announces it the moment it
 * appears, matching this effort's own accessibility requirement. */
export function AuthAlert({ variant = "error", children }: { variant?: AuthAlertVariant; children: React.ReactNode }) {
  const { icon: Icon, classes } = VARIANT_STYLE[variant];
  return (
    <div role="alert" className={cn("flex items-start gap-2 rounded-[var(--radius-md)] p-3 text-sm", classes)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}
