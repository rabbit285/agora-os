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
  closed: "success",
};

export function StatusBadge({ status }: { status: string }) {
  const variant = STATUS_VARIANTS[status] ?? "secondary";
  return <Badge variant={variant}>{status.replace(/_/g, " ")}</Badge>;
}
