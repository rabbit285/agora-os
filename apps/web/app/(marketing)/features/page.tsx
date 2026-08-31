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
  title: "Product — Veyntra",
  description:
    "Document intelligence, control mapping, deterministic assessments, DPIAs, subject access requests, vendor assurance and AI governance — permission-aware throughout.",
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
    id: "document-intelligence",
    title: "Document Intelligence",
    description: "Upload a document once; Veyntra works out where it belongs.",
    items: [
      { icon: TrendingUp, title: "Automatic classification", description: "Each document is read and identified — a privacy notice, a RoPA, a security policy." },
      { icon: TrendingUp, title: "Proposed control mappings", description: "The AI proposes which controls a document evidences, quoting the passage it relied on." },
      { icon: TrendingUp, title: "Verified citations", description: "Every quote is checked against the source document. A quote that isn't there can never be approved." },
    ],
  },
  {
    id: "privacy",
    title: "Privacy & Data Requests",
    description: "DPIA screening through to subject access requests.",
    items: [
      { icon: MessagesSquare, title: "DPIA screening", description: "Processing activities screened against Art. 35(3) and the EDPB's nine criteria." },
      { icon: MessagesSquare, title: "Risk & residual risk", description: "Inherent and residual risk on the same matrix, with unreassessed risks counted at inherent." },
      { icon: MessagesSquare, title: "Subject access requests", description: "Identity verification, real data discovery, and an export that stays blocked until both are done." },
    ],
  },
  {
    id: "vendors",
    title: "Vendor Assurance",
    description: "Review vendors on the evidence they actually provided.",
    items: [
      { icon: Workflow, title: "Questionnaires & documents", description: "Collect what a vendor claims and what they can show." },
      { icon: Workflow, title: "Privacy & security reviews", description: "Separate reviews, each recorded against the evidence on file." },
      { icon: Workflow, title: "Conditional approval", description: "Outstanding evidence produces a conditional approval with stated conditions, not a green tick." },
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
        title="Everything a compliance team needs,"
        accent="in one place"
        description="Document intelligence, control mapping, assessments, privacy workflows and vendor assurance — sharing the same organization, permissions, and audit trail."
      >
        <p className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)]/80 px-4 py-2 text-sm text-[var(--fg-muted)] shadow-[var(--shadow-sm)] backdrop-blur">
          <Gauge className="h-4 w-4 text-[var(--brand-primary)]" aria-hidden="true" />
          Assessments are deterministic — computed from your evidence, never a model&apos;s opinion.
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
