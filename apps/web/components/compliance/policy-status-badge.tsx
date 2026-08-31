import { AlertTriangle, CheckCircle2, CircleDashed, Clock, Info } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { PolicyReviewState, PolicyStatus } from "@/lib/types";

/** A policy's governance status, said once.
 *
 * `draft`/`published` was the whole vocabulary before, which could not
 * distinguish "Veyntra found this document and nobody has looked at the
 * governance yet" from "somebody approved it". The first is where every
 * detected policy starts, and calling it "published" would have been the
 * product asserting an approval nobody gave.
 */
const STATUS: Record<
  PolicyStatus,
  { label: string; variant: "success" | "destructive" | "secondary" | "outline"; icon: typeof Info }
> = {
  approved: { label: "Approved", variant: "success", icon: CheckCircle2 },
  needs_review: { label: "Needs governance review", variant: "secondary", icon: Info },
  draft: { label: "Draft", variant: "outline", icon: CircleDashed },
  review_due: { label: "Review due", variant: "destructive", icon: Clock },
  superseded: { label: "Superseded", variant: "outline", icon: CircleDashed },
  retired: { label: "Retired", variant: "outline", icon: CircleDashed },
};

export function PolicyStatusBadge({ status }: { status: PolicyStatus }) {
  const presentation = STATUS[status] ?? {
    label: status,
    variant: "outline" as const,
    icon: AlertTriangle,
  };
  return (
    <Badge variant={presentation.variant} className="gap-1 whitespace-nowrap">
      <presentation.icon className="h-3 w-3 shrink-0" aria-hidden="true" />
      {presentation.label}
    </Badge>
  );
}

/** The review clock, separately from the approval status.
 *
 * An approved policy whose review lapsed is still approved — whether that
 * breaks a requirement is the framework's call, not a side effect of a
 * date passing. So this is its own badge rather than overwriting the one
 * above.
 */
export function PolicyReviewBadge({
  reviewState,
  daysUntilReview,
}: {
  reviewState: PolicyReviewState;
  /** Computed server-side — see PolicyOut.days_until_review. */
  daysUntilReview: number | null;
}) {
  if (reviewState === "not_applicable" || reviewState === "not_scheduled") return null;

  if (reviewState === "overdue") {
    return (
      <Badge variant="destructive" className="gap-1 whitespace-nowrap">
        <Clock className="h-3 w-3 shrink-0" aria-hidden="true" />
        Review overdue
      </Badge>
    );
  }

  if (reviewState === "due_soon") {
    const days = daysUntilReview === null ? null : Math.max(0, daysUntilReview);
    return (
      <Badge variant="secondary" className="gap-1 whitespace-nowrap">
        <Clock className="h-3 w-3 shrink-0" aria-hidden="true" />
        {days === null ? "Review due soon" : `Review due in ${days} days`}
      </Badge>
    );
  }

  return null;
}
