import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  FileWarning,
  Info,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { ControlAssessmentStatus } from "@/lib/types";

/** A control's effective status — one word, no percentage.
 *
 * This badge used to read "Needs review · 100%", which put an assessment
 * state and an evidence measurement in one place and left the reader to
 * work out that they were different kinds of thing. Worse, the label came
 * from the *derived* assessment, so a control still read "Needs review"
 * after a person had reviewed and passed it.
 *
 * Status now answers "what decision state is this control in", and
 * coverage is rendered separately by whoever shows it. See
 * apps/api/app/compliance/control_assessment.py — the effective status is
 * decided once, on the server, so every screen agrees.
 */
const PRESENTATION: Record<
  ControlAssessmentStatus,
  { variant: "success" | "destructive" | "secondary" | "outline"; icon: typeof Info }
> = {
  // A person passed it. The strongest positive state there is.
  passed: { variant: "success", icon: CheckCircle2 },
  evidenced: { variant: "success", icon: CheckCircle2 },
  partially_implemented: { variant: "secondary", icon: Info },
  partially_evidenced: { variant: "secondary", icon: Info },
  needs_review: { variant: "secondary", icon: Info },
  evidence_insufficient: { variant: "destructive", icon: AlertTriangle },
  failed: { variant: "destructive", icon: XCircle },
  no_evidence: { variant: "destructive", icon: FileWarning },
  not_applicable: { variant: "outline", icon: CircleDashed },
};

const FALLBACK = { variant: "outline" as const, icon: AlertTriangle };

export function AssessmentBadge({
  status,
  label,
}: {
  status: ControlAssessmentStatus;
  /** Phrased server-side, so every surface says the same word. */
  label: string;
}) {
  const presentation = PRESENTATION[status] ?? FALLBACK;
  return (
    <Badge variant={presentation.variant} className="gap-1 whitespace-nowrap">
      {/* The icon differs per state as well as the colour: status must
          never be communicated by colour alone. */}
      <presentation.icon className="h-3 w-3 shrink-0" aria-hidden="true" />
      {label}
    </Badge>
  );
}

/** How much supporting evidence exists, as its own thing.
 *
 * Deliberately quiet and deliberately separate. "—" rather than "0%" when
 * nothing applies: a control with no applicable requirements has no
 * denominator, and printing 0% reads as a failure rather than as out of
 * scope.
 */
export function EvidenceCoverage({
  percent,
  status,
  className,
}: {
  percent: number;
  status: ControlAssessmentStatus;
  className?: string;
}) {
  const notApplicable = status === "not_applicable";

  return (
    <div className={className}>
      <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
        Evidence coverage
      </p>
      <div className="mt-0.5 flex items-center gap-2">
        <span className="text-sm font-medium text-[var(--fg-default)]">
          {notApplicable ? "—" : `${percent}%`}
        </span>
        {!notApplicable && (
          <span
            className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-[var(--gray-200)]"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Evidence coverage"
          >
            <span
              className="block h-full rounded-full bg-[var(--brand-primary)]"
              style={{ width: `${percent}%` }}
            />
          </span>
        )}
      </div>
    </div>
  );
}
