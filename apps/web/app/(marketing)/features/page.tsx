import type { Metadata } from "next";
import {
  Bot,
  Gauge,
  MessagesSquare,
  ScrollText,
  ShieldAlert,
  TrendingUp,
  Workflow,
} from "lucide-react";

import { FeatureGrid, type FeatureItem } from "@/components/marketing/feature-grid";
import { PageHero } from "@/components/marketing/page-hero";

export const metadata: Metadata = {
  title: "Product — Agora Origin",
  description:
    "Compliance, security, sales, support, automation, AI governance, knowledge management, and an AI Copilot — one platform, permission-aware throughout.",
  alternates: { canonical: "/features" },
};

const SECTIONS: { id: string; title: string; description: string; items: FeatureItem[] }[] = [
  {
    id: "compliance",
    title: "Compliance",
    description: "RoPA, DPIA, DSAR, controls, policies, vendor risk, and audits in one place.",
    items: [
      { icon: ScrollText, title: "RoPA & DPIA", description: "Track processing activities and data protection impact assessments end to end." },
      { icon: ScrollText, title: "DSAR handling", description: "Manage subject access requests with clear status and due dates." },
      { icon: ScrollText, title: "Controls & policies", description: "Map controls to frameworks and keep policies current." },
      { icon: ScrollText, title: "Vendor risk & audits", description: "Assess vendors and run audits with a real findings trail." },
      { icon: ScrollText, title: "Regulatory intelligence", description: "Stay aware of the frameworks relevant to your organization." },
    ],
  },
  {
    id: "security",
    title: "Security",
    description: "Assets, findings, alerts, and incidents — with a real path to remediation.",
    items: [
      { icon: ShieldAlert, title: "Asset inventory", description: "Know what you have and what's exposed." },
      { icon: ShieldAlert, title: "Findings & alerts", description: "Real findings from cloud posture and identity checks." },
      { icon: ShieldAlert, title: "Incident response", description: "A structured workspace for timeline, evidence, and root cause." },
      { icon: ShieldAlert, title: "Compliance escalation", description: "A critical incident can create a linked compliance risk automatically." },
    ],
  },
  {
    id: "sales",
    title: "Sales",
    description: "Company and people discovery through to pipeline and meetings.",
    items: [
      { icon: TrendingUp, title: "Company & people discovery", description: "Search and research prospects with ICP scoring." },
      { icon: TrendingUp, title: "Outreach & qualification", description: "Manage sequences with compliance-aware suppression built in." },
      { icon: TrendingUp, title: "Pipeline & meetings", description: "Track opportunities and prep for meetings with AI-assisted notes." },
    ],
  },
  {
    id: "support",
    title: "Customer Support",
    description: "Conversations, ticketing, and SLA tracking with AI assistance.",
    items: [
      { icon: MessagesSquare, title: "Conversations & tickets", description: "One queue for customer conversations and tickets." },
      { icon: MessagesSquare, title: "SLA tracking", description: "Know what's at risk before it breaches." },
      { icon: MessagesSquare, title: "AI summaries & suggestions", description: "Faster responses, grounded in the actual conversation." },
      { icon: MessagesSquare, title: "Escalation", description: "Route urgent issues to the right team automatically." },
    ],
  },
  {
    id: "automation",
    title: "Automation",
    description: "A workflow builder with triggers, approvals, and AI actions.",
    items: [
      { icon: Workflow, title: "Workflow builder", description: "Build multi-step automations without writing code." },
      { icon: Workflow, title: "Triggers & approvals", description: "Sensitive steps wait for a human review by default." },
      { icon: Workflow, title: "Execution history", description: "Every run is logged and auditable." },
    ],
  },
  {
    id: "ai-governance",
    title: "AI Governance",
    description: "Inventory, risk assessment, and evidence for every AI system you use.",
    items: [
      { icon: Bot, title: "AI system inventory", description: "Track every AI system and its risk tier." },
      { icon: Bot, title: "Risk assessment", description: "Structured assessments with real findings." },
      { icon: Bot, title: "Incidents & evidence", description: "A governed record of AI-related incidents." },
    ],
  },
];

export default function FeaturesPage() {
  return (
    <div>
      <PageHero
        eyebrow="Product"
        title="Everything your operations team needs,"
        accent="in one place"
        description="Compliance, security, sales, support, automation, and AI governance — sharing the same organization, permissions, and audit trail."
      >
        <p className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)]/80 px-4 py-2 text-sm text-[var(--fg-muted)] shadow-[var(--shadow-sm)] backdrop-blur">
          <Gauge className="h-4 w-4 text-[var(--brand-primary)]" aria-hidden="true" />
          Plus an AI Copilot that works across every module below.
        </p>
      </PageHero>

      <div className="mx-auto max-w-[var(--content-max-width)] px-4 pb-24 sm:px-6 lg:px-8">
        {/* Each module is a panel rather than a run of headings: this page
            is linked into per-section (/features#security from the module
            cards on the homepage), so a reader usually lands mid-page and
            needs the section they jumped to to be visually self-contained. */}
        <div className="flex flex-col gap-6">
          {SECTIONS.map((section) => (
            <section
              key={section.id}
              id={section.id}
              aria-labelledby={`${section.id}-heading`}
              className="scroll-mt-28 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 sm:p-8"
            >
              <div className="flex items-center gap-3">
                <span
                  aria-hidden="true"
                  className="h-6 w-1 rounded-full bg-[image:var(--gradient-brand)]"
                />
                <h2
                  id={`${section.id}-heading`}
                  className="text-2xl font-semibold tracking-tight text-[var(--fg-default)]"
                >
                  {section.title}
                </h2>
              </div>
              <p className="mt-2 max-w-2xl text-base leading-relaxed text-[var(--fg-muted)]">
                {section.description}
              </p>
              <div className="mt-7 border-t border-[var(--border-default)] pt-7">
                <FeatureGrid items={section.items} />
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
