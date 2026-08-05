import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export type OnboardingStep = { label: string };

/** Generic step indicator — takes labels and a 0-indexed current step so
 * it stays decoupled from onboarding's own 9-screen wiring (which is
 * unchanged by this component; see docs/PUBLIC_SITE_IMPLEMENTATION_PLAN.md
 * Phase 5). Horizontal on desktop, a compact "Step N of M" line on
 * narrow screens rather than cramming 9 labels into one row. */
export function OnboardingStepper({ steps, currentIndex }: { steps: OnboardingStep[]; currentIndex: number }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-[var(--fg-muted)] sm:hidden">
        Step {currentIndex + 1} of {steps.length}: {steps[currentIndex]?.label}
      </p>
      <ol className="hidden items-center gap-1 sm:flex" aria-label="Onboarding progress">
        {steps.map((step, index) => {
          const state = index < currentIndex ? "complete" : index === currentIndex ? "current" : "upcoming";
          return (
            <li key={step.label} className="flex flex-1 items-center gap-1">
              <div
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium",
                  state === "complete" && "bg-[var(--success-600)] text-white",
                  state === "current" && "bg-[var(--brand-primary)] text-white",
                  state === "upcoming" && "bg-[var(--gray-200)] text-[var(--fg-subtle)]",
                )}
                aria-current={state === "current" ? "step" : undefined}
              >
                {state === "complete" ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : index + 1}
              </div>
              {index < steps.length - 1 && (
                <div
                  className={cn(
                    "h-px flex-1",
                    state === "complete" ? "bg-[var(--success-600)]" : "bg-[var(--gray-200)]",
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
