import {
  Bot,
  MessagesSquare,
  ScrollText,
  ShieldAlert,
  TrendingUp,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { CardActionArrow, InteractiveCard } from "@/components/marketing/interactive-card";
import { SectionHeader } from "@/components/marketing/section-header";

type Module = {
  icon: LucideIcon;
  name: string;
  description: string;
  items: string[];
  href: string;
};

const MODULES: Module[] = [
  {
    icon: ScrollText,
    name: "Compliance",
    description: "RoPA, DPIA, DSAR, controls, policies, vendor risk, audits.",
    items: ["Regulatory intelligence", "Framework mapping", "Evidence library"],
    href: "/features#compliance",
  },
  {
    icon: ShieldAlert,
    name: "Security",
    description: "Assets, findings, alerts, incidents, remediation.",
    items: ["Compliance escalation", "Cloud posture", "Identity findings"],
    href: "/features#security",
  },
  {
    icon: TrendingUp,
    name: "Sales",
    description: "Company and people discovery, ICP scoring, research.",
    items: ["Outreach and qualification", "Pipeline", "Meeting prep"],
    href: "/features#sales",
  },
  {
    icon: MessagesSquare,
    name: "Customer Support",
    description: "Conversations, ticketing, SLA tracking.",
    items: ["AI summaries", "Suggested responses", "Escalation"],
    href: "/features#support",
  },
  {
    icon: Workflow,
    name: "Automation",
    description: "Workflow builder, triggers, approvals, AI actions.",
    items: ["Integrations", "Execution history", "Human-in-the-loop approvals"],
    href: "/features#automation",
  },
  {
    icon: Bot,
    name: "AI Governance",
    description: "AI system inventory, risk assessment, incidents.",
    items: ["Evidence", "Governance controls", "Approval workflows"],
    href: "/features#ai-governance",
  },
];

export function ModuleOverview() {
  return (
    <section
      aria-label="Platform modules"
      className="mx-auto max-w-[var(--content-max-width)] px-4 py-20 sm:px-6 lg:px-8"
    >
      <SectionHeader
        eyebrow="Platform"
        title="One operating system, six governed modules"
        description="Every module shares the same organization, permissions, and audit trail — nothing is a bolted-on point tool."
      />
      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {MODULES.map((module) => (
          <InteractiveCard key={module.name} href={module.href} className="p-5">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] bg-[var(--brand-primary-subtle)]">
                <module.icon className="h-4 w-4 text-[var(--brand-primary)]" aria-hidden="true" />
              </div>
              <h3 className="text-sm font-semibold text-[var(--fg-default)] transition-colors duration-[var(--transition-card)] ease-[var(--ease-card)] group-hover:text-[var(--brand-primary)]">
                {module.name}
              </h3>
              <CardActionArrow className="ml-auto text-[var(--fg-subtle)] group-hover:text-[var(--brand-primary)]" />
            </div>
            <p className="mt-3 text-sm leading-relaxed text-[var(--fg-muted)]">
              {module.description}
            </p>
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {module.items.map((item) => (
                <li
                  key={item}
                  className="rounded-[var(--radius-sm)] bg-[var(--bg-sunken)] px-2 py-1 text-xs text-[var(--fg-muted)]"
                >
                  {item}
                </li>
              ))}
            </ul>
          </InteractiveCard>
        ))}
      </div>
    </section>
  );
}
