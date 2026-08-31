import type { Metadata } from "next";
import { Bot, FileWarning, Gauge, ShieldCheck } from "lucide-react";

import { CustomerTypeSection } from "@/components/marketing/customer-type-section";
import { FinalCTA } from "@/components/marketing/final-cta";
import { HeroSection } from "@/components/marketing/hero-section";
import { IntegrationGrid } from "@/components/marketing/integration-grid";
import { ModuleCarousel } from "@/components/marketing/module-carousel";
import { ModuleOverview } from "@/components/marketing/module-overview";
import { PricingPreview } from "@/components/marketing/pricing-preview";
import { SectionHeader } from "@/components/marketing/section-header";
import { TrustSection } from "@/components/marketing/trust-section";
import { WorkflowExample } from "@/components/marketing/workflow-example";
import { WorldMapBackdropLazy } from "@/components/marketing/world-map-backdrop-lazy";

export const metadata: Metadata = {
  title: "Veyntra — Upload once. AI does the compliance work.",
  description:
    "Veyntra reads your policies, proposes which controls they evidence, and shows you exactly where the gaps are — for GDPR, the EU AI Act, ISO 27001, NIS2, DORA and SOC 2.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Veyntra — Upload once. AI does the compliance work.",
    description:
      "AI-proposed control mappings with verified citations. You approve every one.",
    url: "/",
    type: "website",
  },
};

const HOW_IT_WORKS = [
  { step: "1", title: "Choose your frameworks", description: "Adopt GDPR, the EU AI Act, ISO 27001, NIS2, DORA or SOC 2. Veyntra builds the control set for you." },
  { step: "2", title: "Upload your documents", description: "Policies, notices, procedures. Veyntra reads each one, works out what it is, and finds the controls it evidences." },
  { step: "3", title: "Approve the mappings", description: "Every proposal quotes the passage it relied on, and the quote is checked against your document before you see it." },
  { step: "4", title: "See what's actually missing", description: "A readiness score that shows its arithmetic, gaps that name the evidence they need, and tasks to close them." },
];

export default function HomePage() {
  return (
    <>
      <HeroSection />

      {/* The problem this product solves is a global one, so the section
          makes that literal: a dot-matrix world map lit by the brand
          sweep, sitting behind the copy. Decorative and lazily loaded —
          see WorldMapBackdropLazy. */}
      <section className="relative isolate overflow-hidden">
        <WorldMapBackdropLazy />
        {/* Holds contrast for the copy, which sits directly over the
            densest part of the map (Eurasia). Deliberately veils rather
            than blanks: at full opacity it punched a hole in the middle of
            the map and the graphic stopped reading as one. Inline style
            because the stop uses color-mix, whose commas fight Tailwind's
            arbitrary-value parser. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(58% 68% at 50% 52%, color-mix(in srgb, var(--bg-app) 88%, transparent) 30%, transparent 100%)",
          }}
        />
        <div className="relative mx-auto max-w-[var(--content-max-width)] px-4 py-28 sm:px-6 lg:px-8">
          <SectionHeader
            eyebrow="The problem"
            title="Compliance evidence lives in a spreadsheet nobody trusts"
            description="Policies sit in one drive, the control list in another, and the link between them exists only in somebody's memory — until an auditor asks."
          />
          <div className="mx-auto mt-12 grid max-w-3xl gap-6 sm:grid-cols-2">
            {[
              { icon: FileWarning, text: "Fragmented information across tools nobody fully trusts" },
              { icon: Gauge, text: "Manual work that should have been automated months ago" },
              { icon: ShieldCheck, text: "Slow decisions because nobody has the full picture" },
              { icon: Bot, text: "Higher operational risk from gaps between systems" },
            ].map((item) => (
              <div key={item.text} className="flex items-start gap-3">
                <item.icon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--critical-500)]" aria-hidden="true" />
                <p className="text-sm text-[var(--fg-muted)]">{item.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <ModuleOverview />

      <ModuleCarousel />

      <section className="mx-auto max-w-[var(--content-max-width)] px-4 py-20 sm:px-6 lg:px-8">
        <SectionHeader eyebrow="How it works" title="From connected data to reviewed action" />
        <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {HOW_IT_WORKS.map((item) => (
            <div key={item.step}>
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--brand-primary)] text-sm font-semibold text-white">
                {item.step}
              </div>
              <h3 className="mt-3 text-sm font-semibold text-[var(--fg-default)]">{item.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-[var(--fg-muted)]">{item.description}</p>
            </div>
          ))}
        </div>
        <p className="mx-auto mt-10 max-w-2xl text-center text-sm text-[var(--fg-muted)]">
          Veyntra can analyze, recommend, and prepare actions, while important changes remain
          permission-aware, reviewable, and auditable.
        </p>
      </section>

      <section className="border-y border-[var(--border-default)] bg-[var(--bg-app)]">
        <div className="mx-auto max-w-[var(--content-max-width)] px-4 py-20 sm:px-6 lg:px-8">
          <SectionHeader
            eyebrow="AI Copilot"
            title="One assistant, grounded in your own data"
            description="The Copilot answers questions across authorized business data, summarizes risk and activity, and prepares tasks and workflows — never a fully autonomous actor when human approval is required."
          />
          <ul className="mx-auto mt-10 grid max-w-2xl gap-3 sm:grid-cols-2">
            {[
              "Answers questions across authorized business data",
              "Summarizes risks and activity",
              "Recommends next actions",
              "Prepares tasks and workflows",
              "Cites its sources",
              "Requests approval before sensitive actions",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2.5 text-sm text-[var(--fg-muted)]">
                <Bot className="mt-0.5 h-4 w-4 shrink-0 text-[var(--ai-600)]" aria-hidden="true" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="mx-auto max-w-[var(--content-max-width)] px-4 py-20 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Cross-module value"
          title="Modules that actually talk to each other"
          description="A handful of the real, working connections between modules — not a diagram of what might happen someday."
        />
        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          <WorkflowExample
            steps={[{ module: "Security", label: "Security" }, { module: "Compliance", label: "Compliance" }]}
            description="A critical security incident automatically creates a linked compliance risk for review."
          />
          <WorkflowExample
            steps={[{ module: "Compliance", label: "Documents" }, { module: "Compliance", label: "Evidence" }]}
            description="An uploaded policy is read, classified, and proposed as evidence against the controls it actually supports."
          />
          <WorkflowExample
            steps={[{ module: "Compliance", label: "Evidence" }, { module: "Compliance", label: "Assessment" }]}
            description="Approving a mapping marks the control for reassessment — the previous conclusion is never silently rewritten."
          />
          <WorkflowExample
            steps={[{ module: "Compliance", label: "Gap" }, { module: "Compliance", label: "Task" }]}
            description="A gap becomes an owned, dated task linked back to the requirement and control that produced it."
          />
        </div>
      </section>

      <TrustSection />

      <section className="mx-auto max-w-[var(--content-max-width)] px-4 py-20 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Integrations"
          title="Connect the tools you already use"
          description="Every integration below is real, working code — connect it from Settings once you're in."
        />
        <div className="mt-10">
          <IntegrationGrid />
        </div>
      </section>

      <CustomerTypeSection />

      <section className="mx-auto max-w-[var(--content-max-width)] px-4 py-20 sm:px-6 lg:px-8">
        <SectionHeader eyebrow="Pricing" title="Simple plans that grow with you" />
        <div className="mt-10">
          <PricingPreview />
        </div>
      </section>

      <FinalCTA />
    </>
  );
}
