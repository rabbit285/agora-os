import type { Metadata } from "next";

import { CustomerTypeSection } from "@/components/marketing/customer-type-section";
import { SectionHeader } from "@/components/marketing/section-header";
import { WorkflowExample } from "@/components/marketing/workflow-example";

export const metadata: Metadata = {
  title: "Solutions — Agora Origin",
  description: "How Agora Origin fits growing, regulated European businesses across compliance, security, sales, and support.",
  alternates: { canonical: "/solutions" },
};

const SOLUTIONS = [
  {
    title: "Compliance and security teams",
    description:
      "Replace spreadsheets and scattered evidence with a governed system of record for RoPA, DPIA, controls, and findings — with a real link between a security incident and the compliance risk it creates.",
  },
  {
    title: "Revenue teams",
    description:
      "Research and qualify companies and people, run outreach with built-in suppression and compliance gating, and keep pipeline visibility without a separate CRM export.",
  },
  {
    title: "Customer-facing teams",
    description:
      "Track conversations and tickets against real SLAs, with AI-drafted summaries and suggested responses grounded in the actual thread — and a clear escalation path to Security when something warrants it.",
  },
  {
    title: "Operations leaders",
    description:
      "See compliance readiness, security posture, sales pipeline, and automation activity in one command center, with an AI Copilot that can explain what changed and why.",
  },
];

export default function SolutionsPage() {
  return (
    <div>
      <div className="mx-auto max-w-[var(--content-max-width)] px-4 py-16 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Solutions"
          title="Built for the teams that keep a growing business governed"
          description="Agora Origin adapts to how your teams already work, without asking them to abandon the tools that already fit."
        />

        <div className="mx-auto mt-14 grid max-w-4xl gap-8 sm:grid-cols-2">
          {SOLUTIONS.map((solution) => (
            <div key={solution.title}>
              <h2 className="text-base font-semibold text-[var(--fg-default)]">{solution.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-[var(--fg-muted)]">{solution.description}</p>
            </div>
          ))}
        </div>

        <div className="mx-auto mt-16 max-w-2xl">
          <h2 className="text-center text-base font-semibold text-[var(--fg-default)]">
            A real example of a cross-team flow
          </h2>
          <div className="mt-6">
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
