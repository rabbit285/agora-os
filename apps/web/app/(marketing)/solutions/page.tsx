import type { Metadata } from "next";
import { Gauge, MessagesSquare, ShieldCheck, TrendingUp } from "lucide-react";

import { CustomerTypeSection } from "@/components/marketing/customer-type-section";
import { PageHero } from "@/components/marketing/page-hero";
import { WorkflowExample } from "@/components/marketing/workflow-example";

export const metadata: Metadata = {
  title: "Solutions — Agora Origin",
  description: "How Agora Origin fits growing, regulated businesses across compliance, security, sales, and support.",
  alternates: { canonical: "/solutions" },
};

const SOLUTIONS = [
  {
    icon: ShieldCheck,
    title: "Compliance and security teams",
    description:
      "Replace spreadsheets and scattered evidence with a governed system of record for RoPA, DPIA, controls, and findings — with a real link between a security incident and the compliance risk it creates.",
  },
  {
    icon: TrendingUp,
    title: "Revenue teams",
    description:
      "Research and qualify companies and people, run outreach with built-in suppression and compliance gating, and keep pipeline visibility without a separate CRM export.",
  },
  {
    icon: MessagesSquare,
    title: "Customer-facing teams",
    description:
      "Track conversations and tickets against real SLAs, with AI-drafted summaries and suggested responses grounded in the actual thread — and a clear escalation path to Security when something warrants it.",
  },
  {
    icon: Gauge,
    title: "Operations leaders",
    description:
      "See compliance readiness, security posture, sales pipeline, and automation activity in one command center, with an AI Copilot that can explain what changed and why.",
  },
];

export default function SolutionsPage() {
  return (
    <div>
      <PageHero
        eyebrow="Solutions"
        title="Built for the teams that keep a growing business"
        accent="governed"
        description="Agora Origin adapts to how your teams already work, without asking them to abandon the tools that already fit."
      />

      <div className="mx-auto max-w-[var(--content-max-width)] px-4 pb-24 sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-5xl gap-5 sm:grid-cols-2">
          {SOLUTIONS.map((solution) => (
            <div
              key={solution.title}
              className="rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6"
            >
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-[var(--radius-md)] bg-[var(--brand-primary-subtle)]">
                <solution.icon
                  className="h-5 w-5 text-[var(--brand-primary)]"
                  aria-hidden="true"
                />
              </span>
              <h2 className="mt-4 text-lg font-semibold text-[var(--fg-default)]">
                {solution.title}
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-[var(--fg-muted)]">
                {solution.description}
              </p>
            </div>
          ))}
        </div>

        <div className="mx-auto mt-20 max-w-2xl text-center">
          <p className="flex items-center justify-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
            <span
              aria-hidden="true"
              className="h-3 w-1 rounded-full bg-[image:var(--gradient-arc-teal)]"
            />
            In practice
          </p>
          <h2 className="mt-3 text-[length:var(--text-3xl)] font-semibold tracking-tight text-[var(--fg-default)]">
            A real example of a cross-team flow
          </h2>
          <div className="mt-8 text-left">
            <WorkflowExample
              steps={[
                { module: "Sales", label: "Sales" },
                { module: "Compliance", label: "Compliance" },
              ]}
              description="A new enterprise opportunity above a configured threshold can create a security-review task in Compliance automatically — so the deal isn't blocked at the finish line."
            />
          </div>
        </div>
      </div>

      <CustomerTypeSection />
    </div>
  );
}
