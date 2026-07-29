import { Badge } from "@/components/ui/badge";
import type { Severity } from "@/lib/types";

const SEVERITY_VARIANTS: Record<Severity, "secondary" | "warning" | "destructive"> = {
  low: "secondary",
  medium: "secondary",
  high: "warning",
  critical: "destructive",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge variant={SEVERITY_VARIANTS[severity]}>{severity}</Badge>;
}
