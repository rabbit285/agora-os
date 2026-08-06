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
import { SectionHeader } from "@/components/marketing/section-header";

export const metadata: Metadata = {
  title: "Product — Agora Origin",
  description:
    "Compliance, security, sales, support, automation, AI governance, knowledge management, and an AI Copilot — one platform, permission-aware throughout.",
  alternates: { canonical: "/features" },
};

const SECTIONS: { title: string; description: string; items: FeatureItem[] }[] = [
  {
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
    title: "Sales",
    description: "Company and people discovery through to pipeline and meetings.",
    items: [
      { icon: TrendingUp, title: "Company & people discovery", description: "Search and research prospects with ICP scoring." },
      { icon: TrendingUp, title: "Outreach & qualification", description: "Manage sequences with compliance-aware suppression built in." },
      { icon: TrendingUp, title: "Pipeline & meetings", description: "Track opportunities and prep for meetings with AI-assisted notes." },
    ],
  },
  {
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
    title: "Automation",
    description: "A workflow builder with triggers, approvals, and AI actions.",
    items: [
      { icon: Workflow, title: "Workflow builder", description: "Build multi-step automations without writing code." },
      { icon: Workflow, title: "Triggers & approvals", description: "Sensitive steps wait for a human review by default." },
      { icon: Workflow, title: "Execution history", description: "Every run is logged and auditable." },
    ],
  },
  {
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
    <div className="mx-auto max-w-[var(--content-max-width)] px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeader
        eyebrow="Product"
        title="Everything your operations team needs, in one place"
        description="Compliance, security, sales, support, automation, and AI governance — sharing the same organization, permissions, and audit trail."
        align="left"
        className="max-w-2xl mx-0 text-left"
      />
      <div className="mt-4 flex items-center gap-2 text-sm text-[var(--fg-muted)]">
        <Gauge className="h-4 w-4" aria-hidden="true" />
        Plus an AI Copilot that works across every module below.
      </div>

      <div className="mt-16 flex flex-col gap-16">
        {SECTIONS.map((section) => (
          <div key={section.title}>
            <h2 className="text-xl font-semibold text-[var(--fg-default)]">{section.title}</h2>
            <p className="mt-1 max-w-xl text-sm text-[var(--fg-muted)]">{section.description}</p>
            <div className="mt-6">
              <FeatureGrid items={section.items} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
