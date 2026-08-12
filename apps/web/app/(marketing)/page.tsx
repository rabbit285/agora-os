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
  title: "Veyntra — The secure AI operating system for SMEs",
  description:
    "Veyntra helps SMEs manage compliance, reduce security risk, find customers, support users, and automate daily operations from one intelligent workspace.",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Veyntra — The secure AI operating system for SMEs",
    description:
      "Compliance, security, sales, support, and automation — from one governed workspace.",
    url: "/",
    type: "website",
  },
};

const HOW_IT_WORKS = [
  { step: "1", title: "Connect your business tools", description: "Bring in CRM, calendar, mail, and engineering data through read-only or configurable integrations." },
  { step: "2", title: "Understand risks and opportunities", description: "Veyntra surfaces compliance gaps, security findings, and sales signals across your data." },
  { step: "3", title: "Receive AI-assisted recommendations", description: "The AI Copilot proposes next actions, grounded in your organization's own records." },
  { step: "4", title: "Review, approve, and automate", description: "Nothing sensitive runs without a human review — approved actions become repeatable automations." },
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
            title="Growing SMEs run on disconnected tools"
            description="Compliance, security, sales, support, automation, and reporting usually live in five different systems that don't talk to each other."
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
            steps={[{ module: "Support", label: "Support" }, { module: "Security", label: "Security" }]}
            description="A support escalation involving a security concern notifies the Security team directly."
          />
          <WorkflowExample
            steps={[{ module: "Support", label: "Support" }, { module: "Sales", label: "Sales" }]}
            description="An upsell signal detected in a support conversation can create a qualified Sales lead."
          />
          <WorkflowExample
            steps={[{ module: "Sales", label: "Sales" }, { module: "Compliance", label: "Compliance" }]}
            description="A new enterprise opportunity can trigger a compliance security-review task automatically."
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
