import { CheckCircle2, Loader2, XCircle } from "lucide-react";

export type VerificationStatus = "pending" | "success" | "error";

const STATUS_CONFIG: Record<VerificationStatus, { icon: typeof Loader2; classes: string; spin?: boolean }> = {
  pending: { icon: Loader2, classes: "text-[var(--brand-primary)]", spin: true },
  success: { icon: CheckCircle2, classes: "text-[var(--success-600)]" },
  error: { icon: XCircle, classes: "text-[var(--critical-600)]" },
};

/** Shared status display for any "we're processing a token" flow —
 * email verification today, reusable for anything with the same
 * pending/success/error shape later. */
export function VerificationState({
  status,
  title,
  description,
  action,
}: {
  status: VerificationStatus;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  const { icon: Icon, classes, spin } = STATUS_CONFIG[status];
  return (
    <div className="flex flex-col items-center gap-3 py-4 text-center">
      <Icon className={`h-10 w-10 ${classes} ${spin ? "animate-spin" : ""}`} aria-hidden="true" />
      <h2 className="text-base font-semibold text-[var(--fg-default)]">{title}</h2>
      {description && <p className="text-sm text-[var(--fg-muted)]">{description}</p>}
      {action}
    </div>
  );
}
