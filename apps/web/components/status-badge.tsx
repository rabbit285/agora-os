import { Badge } from "@/components/ui/badge";

const STATUS_VARIANTS: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "destructive" | "outline"
> = {
  open: "secondary",
  in_progress: "warning",
  done: "success",
  cancelled: "outline",
  pending: "warning",
  approved: "success",
  rejected: "destructive",
  expired: "outline",
  processing: "warning",
  ready: "success",
  failed: "destructive",
  unsupported_format: "outline",
  not_started: "outline",
  implemented: "success",
  needs_review: "warning",
  pass: "success",
  fail: "destructive",
  partial: "warning",
  not_assessed: "outline",
  mitigated: "success",
  accepted: "secondary",
  healthy: "success",
  at_risk: "warning",
  compromised: "destructive",
  new: "warning",
  investigating: "warning",
  contained: "secondary",
  resolved: "success",
  false_positive: "outline",
  risk_accepted: "secondary",
  detected: "destructive",
  triage: "warning",
  containment: "warning",
  eradication: "warning",
  recovery: "secondary",
  postmortem: "secondary",
  prospect: "secondary",
  customer: "success",
  churned: "outline",
  qualified: "success",
  contacted: "warning",
  disqualified: "outline",
  converted: "success",
  prospecting: "secondary",
  qualification: "warning",
  proposal: "warning",
  negotiation: "warning",
  closed_won: "success",
  closed_lost: "destructive",
  draft: "outline",
  sent: "success",
  blocked: "destructive",
  billing: "secondary",
  technical: "secondary",
  account: "secondary",
  security: "destructive",
  general: "outline",
  low: "outline",
  medium: "secondary",
  high: "warning",
  urgent: "destructive",
  active: "success",
  testing: "warning",
  paused: "secondary",
  archived: "outline",
  running: "warning",
  succeeded: "success",
  awaiting_approval: "warning",
  disabled: "outline",
  connected: "success",
  not_connected: "outline",
  disconnected: "outline",
  error: "destructive",
  ok: "success",
  in_review: "warning",
  // Not a failure and not progress: something has to be filled in before
  // the work can count for anything. Warning rather than destructive,
  // because nothing is broken — a step was skipped.
  needs_setup: "warning",
  ready_to_share: "success",
  retired: "outline",
  minimal: "outline",
  limited: "secondary",
  unacceptable: "destructive",
  received: "secondary",
  fulfilled: "success",
  under_review: "warning",
  offboarded: "outline",
  missing: "destructive",
  planned: "outline",
  remediated: "success",
  independently_assessed: "secondary",
  certified: "success",
  cleared: "success",
  security_review: "warning",
  terminated: "destructive",
  not_configured: "outline",
  ready_to_connect: "secondary",
  syncing: "warning",
  degraded: "warning",
  rate_limited: "warning",
  revoked: "destructive",
  demo: "secondary",
  user_entered: "secondary",
  provider_supplied: "success",
  requires_review: "warning",
  unknown: "outline",
  // Requirement states, from app.compliance.assessment. The audit
  // workspace shows these against every scoped requirement.
  evidence_missing: "destructive",
  assessment_failed: "destructive",
  deficient: "warning",
  satisfied: "success",
  // Audit finding lifecycle. "Ready for verification" is warning rather
  // than success on purpose: the work is done and nobody has checked it,
  // which is a state that still wants somebody's attention.
  remediation_in_progress: "warning",
  ready_for_verification: "warning",
  closed: "success",
  accepted_risk: "outline",
};

export function StatusBadge({
  status,
  label,
}: {
  /** Nullable on purpose. Several statuses in this product mean
   * "nobody has decided yet", and a badge is not the place to crash
   * over one — this renders nothing rather than taking the page with
   * it. Callers that want to *say* something about the absence pass a
   * `label`. */
  status: string | null | undefined;
  /** The server's wording for this state, where it has one.
   *
   * Several vocabularies here read badly when de-underscored:
   * "not assessed" is not what `not_assessed` means to an auditor — the
   * requirement has no control mapped to it. Where the API sends words
   * chosen for the reader, they win over the ones derived from the key. */
  label?: string | null;
}) {
  const text = label || (status ? status.replace(/_/g, " ") : "");
  if (!text) return null;
  const variant = (status ? STATUS_VARIANTS[status] : undefined) ?? "secondary";
  return <Badge variant={variant}>{text}</Badge>;
}
