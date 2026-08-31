import { Badge } from "@/components/ui/badge";

/** Priority, said the way a product says it.
 *
 * The API's vocabulary is `high` / `medium` / `low` (and `normal` /
 * `urgent` on tasks) because those are stable values to filter and store
 * on. Rendering the stored value directly is how screens ended up
 * showing `priority: high` — a database column pasted into a badge. This
 * is the one place that translation happens. */
const LABEL: Record<string, string> = {
  urgent: "Urgent",
  high: "High priority",
  medium: "Medium priority",
  normal: "Normal priority",
  low: "Low priority",
};

const VARIANT: Record<string, "destructive" | "outline" | "secondary"> = {
  urgent: "destructive",
  high: "destructive",
  medium: "outline",
  normal: "outline",
  low: "secondary",
};

export function PriorityBadge({ priority }: { priority: string }) {
  return (
    <Badge variant={VARIANT[priority] ?? "secondary"}>
      {LABEL[priority] ?? "Normal priority"}
    </Badge>
  );
}
