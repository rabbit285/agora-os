import { ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

export type WorkflowStep = { module: string; label: string };

/** A single cross-module flow: a short chain of module badges connected by
 * arrows, plus one sentence of plain description. Used by the homepage's
 * cross-module value section — deliberately simple (no diagramming
 * library), since the point is legibility, not decoration. */
export function WorkflowExample({ steps, description }: { steps: WorkflowStep[]; description: string }) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center gap-2">
        {steps.map((step, index) => (
          <div key={`${step.module}-${index}`} className="flex items-center gap-2">
            <Badge variant={index === steps.length - 1 ? "success" : "secondary"}>{step.module}</Badge>
            {index < steps.length - 1 && (
              <ArrowRight className="h-3.5 w-3.5 text-[var(--fg-subtle)]" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>
      <p className="mt-3 text-sm leading-relaxed text-[var(--fg-muted)]">{description}</p>
    </Card>
  );
}
