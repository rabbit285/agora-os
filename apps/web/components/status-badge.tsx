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
};

export function StatusBadge({ status }: { status: string }) {
  const variant = STATUS_VARIANTS[status] ?? "secondary";
  return <Badge variant={variant}>{status.replace(/_/g, " ")}</Badge>;
}
